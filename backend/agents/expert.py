"""A single recursively-spawning expert agent.

Each expert is given:
  - a focused goal
  - a list of tools (MCP function descriptors) it may call
  - a budget (max sub-agents, max depth) it must respect

It may, in turn, decide to spawn sub-experts. The orchestrator enforces the
global cap on parallelism and depth.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..llm.router import LLMRequest, LLMRouter, TaskProfile
from ..llm.providers.base import Message

log = logging.getLogger(__name__)


SpawnFn = Callable[["AgentSpec"], Awaitable["AgentResult"]]


@dataclass
class AgentSpec:
    name: str
    goal: str
    expertise: str = "general"
    tools: List[str] = field(default_factory=list)
    parent: Optional[str] = None
    depth: int = 0
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    agent: str
    success: bool
    output: str
    sub_results: List["AgentResult"] = field(default_factory=list)
    error: Optional[str] = None


PLANNER_SYSTEM = """You are an expert sub-agent in a recursive agent system.

Your job:
1. Read your goal carefully.
2. Decide if you can answer it directly OR if you need to delegate parts of it
   to specialized sub-agents.
3. If delegating, output a JSON plan of sub-agents to spawn (max {max_fanout}).
4. Otherwise, output your final answer.

Always reply with a single JSON object of the form:
{{
  "decision": "answer" | "delegate",
  "answer": "<final text if decision == 'answer'>",
  "sub_agents": [
    {{ "name": "...", "expertise": "...", "goal": "...", "tools": ["..."] }}
  ],
  "rationale": "<one-line reason>"
}}

You are at depth {depth} of {max_depth}. If depth >= max_depth-1, you MUST
choose "answer" — no more delegation.
"""


class ExpertAgent:
    def __init__(
        self,
        spec: AgentSpec,
        router: LLMRouter,
        spawn_fn: SpawnFn,
        max_fanout: int,
        max_depth: int,
    ):
        self.spec = spec
        self.router = router
        self.spawn_fn = spawn_fn
        self.max_fanout = max_fanout
        self.max_depth = max_depth

    async def run(self) -> AgentResult:
        log.info(
            "[%s] depth=%d goal=%r", self.spec.name, self.spec.depth, self.spec.goal
        )
        try:
            plan = await self._plan()
        except Exception as e:
            return AgentResult(
                agent=self.spec.name,
                success=False,
                output="",
                error=f"planning failed: {e}",
            )

        decision = plan.get("decision", "answer")

        if decision == "answer" or self.spec.depth >= self.max_depth - 1:
            return AgentResult(
                agent=self.spec.name,
                success=True,
                output=plan.get("answer") or plan.get("rationale", ""),
            )

        sub_specs = plan.get("sub_agents") or []
        sub_specs = sub_specs[: self.max_fanout]
        children = [
            AgentSpec(
                name=s.get("name", f"{self.spec.name}-child{i}"),
                goal=s.get("goal", ""),
                expertise=s.get("expertise", "general"),
                tools=s.get("tools", []),
                parent=self.spec.name,
                depth=self.spec.depth + 1,
                context=self.spec.context,
            )
            for i, s in enumerate(sub_specs)
        ]

        sub_results = await asyncio.gather(
            *(self.spawn_fn(c) for c in children),
            return_exceptions=False,
        )

        synthesis = await self._synthesize(sub_results)
        return AgentResult(
            agent=self.spec.name,
            success=True,
            output=synthesis,
            sub_results=list(sub_results),
        )

    # ------------------------------------------------------------------ planning
    async def _plan(self) -> Dict[str, Any]:
        system = PLANNER_SYSTEM.format(
            max_fanout=self.max_fanout,
            depth=self.spec.depth,
            max_depth=self.max_depth,
        )
        user = (
            f"Your name: {self.spec.name}\n"
            f"Your expertise: {self.spec.expertise}\n"
            f"Available tools: {', '.join(self.spec.tools) or '(none)'}\n"
            f"Goal: {self.spec.goal}\n"
            f"Context: {json.dumps(self.spec.context)[:1500]}"
        )
        resp = await self.router.complete(
            LLMRequest(
                user=user,
                system=system,
                task=TaskProfile.for_deep_reasoning(),
                json_mode=True,
                max_tokens=1500,
            )
        )
        text = resp.text.strip()
        # Tolerant JSON extraction
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            return {"decision": "answer", "answer": text}

    async def _synthesize(self, sub_results: List[AgentResult]) -> str:
        bullets = "\n".join(
            f"- [{r.agent}] {'OK' if r.success else 'FAIL'}: {r.output[:600]}"
            for r in sub_results
        )
        resp = await self.router.complete(
            LLMRequest(
                user=(
                    f"Original goal: {self.spec.goal}\n\n"
                    f"Sub-agent reports:\n{bullets}\n\n"
                    "Synthesize a single, decisive answer to the goal. "
                    "No bullet lists, no headers — just the answer."
                ),
                system="You are a senior agent synthesizing reports from your team.",
                task=TaskProfile.for_deep_reasoning(),
                max_tokens=1200,
            )
        )
        return resp.text.strip()

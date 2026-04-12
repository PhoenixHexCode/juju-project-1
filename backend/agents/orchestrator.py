"""Top-level agent orchestrator.

Enforces global parallelism cap, depth cap, and per-agent timeout.
The companion's main loop calls `Orchestrator.handle_request()` which:
  1. Drops a root expert agent on the goal.
  2. The root may spawn children, each of which may spawn more — bounded.
  3. Returns a flat AgentRunReport tree for logging / UI display.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import get_settings
from ..llm.router import LLMRouter
from .expert import AgentResult, AgentSpec, ExpertAgent

log = logging.getLogger(__name__)


@dataclass
class AgentRunReport:
    goal: str
    final_answer: str
    elapsed_seconds: float
    total_agents_spawned: int
    tree: AgentResult
    truncated: bool = False


class Orchestrator:
    def __init__(self, router: LLMRouter, mcp_tools: Optional[List[str]] = None):
        s = get_settings()
        self.router = router
        self.max_parallel = s.agent_max_parallel
        self.max_depth = s.agent_max_depth
        self.timeout = s.agent_timeout_seconds
        self.mcp_tools = mcp_tools or []

        self._sema = asyncio.Semaphore(self.max_parallel)
        self._spawn_count = 0
        self._truncated = False

    async def handle_request(
        self,
        user_goal: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentRunReport:
        self._spawn_count = 0
        self._truncated = False
        start = time.time()

        root_spec = AgentSpec(
            name="root",
            goal=user_goal,
            expertise="general orchestrator",
            tools=self.mcp_tools,
            depth=0,
            context=context or {},
        )

        try:
            tree = await asyncio.wait_for(self._spawn(root_spec), timeout=self.timeout)
        except asyncio.TimeoutError:
            tree = AgentResult(
                agent="root",
                success=False,
                output="(timed out)",
                error=f"orchestrator exceeded {self.timeout}s",
            )
            self._truncated = True

        return AgentRunReport(
            goal=user_goal,
            final_answer=tree.output,
            elapsed_seconds=round(time.time() - start, 2),
            total_agents_spawned=self._spawn_count,
            tree=tree,
            truncated=self._truncated,
        )

    # ------------------------------------------------------------------- spawn
    async def _spawn(self, spec: AgentSpec) -> AgentResult:
        # Hard global cap on agents per request
        if self._spawn_count >= self.max_parallel * (self.max_depth + 1):
            self._truncated = True
            return AgentResult(
                agent=spec.name,
                success=False,
                output="(skipped — global agent cap reached)",
            )

        async with self._sema:
            self._spawn_count += 1
            agent = ExpertAgent(
                spec=spec,
                router=self.router,
                spawn_fn=self._spawn,
                max_fanout=self.max_parallel,
                max_depth=self.max_depth,
            )
            return await agent.run()

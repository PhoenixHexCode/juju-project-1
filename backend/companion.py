"""The Companion: pulls together LLM router, memory, agents, MCP, and voice
into a single object that the API layer can hold onto.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .agents import AgentRunReport, Orchestrator
from .config import get_settings
from .llm.providers.base import Message
from .llm.router import LLMRequest, LLMRouter, TaskProfile
from .mcp_server import HostBridgeClient, build_mcp_server, detect_device
from .mcp_server.server import ToolRegistry
from .memory import MemoryStore
from .security.permissions import PermissionBroker
from .voice.persona import persona_system_prompt
from .voice.stt import SpeechToText
from .voice.tts import TextToSpeech

log = logging.getLogger(__name__)


@dataclass
class CompanionReply:
    text: str
    provider: str
    model: str
    used_agents: bool
    agent_report: Optional[AgentRunReport] = None


class Companion:
    def __init__(self):
        self.settings = get_settings()
        self.router = LLMRouter()
        self.memory = MemoryStore()
        self.permissions = PermissionBroker()
        self.host_bridge = HostBridgeClient.from_env()
        self.tools: ToolRegistry = build_mcp_server(
            permissions=self.permissions, host_bridge=self.host_bridge
        )
        self.orchestrator = Orchestrator(
            router=self.router,
            mcp_tools=[t["name"] for t in self.tools.list()],
        )
        self.stt = SpeechToText()
        self.tts = TextToSpeech()
        self.device = detect_device()

        log.info("Companion online. device=%s providers=%s tools=%d",
                 self.device.kind, self.router.available_providers,
                 len(self.tools.list()))

    # ------------------------------------------------------------------ chat
    async def chat(
        self,
        user_id: str,
        text: str,
        *,
        voice_mode: bool = False,
    ) -> CompanionReply:
        # Persist user turn
        self.memory.add(user_id, text, role="user", kind="message")

        # Decide if this is a complex task that warrants the agent swarm
        complex_task = await self._is_complex_task(text)

        if complex_task:
            report = await self.orchestrator.handle_request(
                user_goal=text,
                context={"user_id": user_id, "device": self.device.kind},
            )
            answer = report.final_answer
            self.memory.add(user_id, answer, role="assistant", kind="message",
                            meta={"agents": report.total_agents_spawned,
                                  "elapsed": report.elapsed_seconds})
            return CompanionReply(
                text=answer,
                provider="multi-agent",
                model=f"{report.total_agents_spawned} agents",
                used_agents=True,
                agent_report=report,
            )

        # Simple turn — single LLM call with persona + memory context
        memory_block = self.memory.context_block(user_id, text)
        system = persona_system_prompt() + "\n\n" + memory_block
        history: List[Message] = []  # memory_block already injects history

        task = TaskProfile.for_voice_turn() if voice_mode else TaskProfile()
        resp = await self.router.complete(
            LLMRequest(
                user=text,
                system=system,
                history=history,
                task=task,
                max_tokens=self.settings.llm_max_tokens,
            )
        )
        self.memory.add(user_id, resp.text, role="assistant", kind="message",
                        meta={"provider": resp.provider, "model": resp.model})
        return CompanionReply(
            text=resp.text,
            provider=resp.provider,
            model=resp.model,
            used_agents=False,
        )

    # ------------------------------------------------------------------ helper
    async def _is_complex_task(self, text: str) -> bool:
        """Tiny classifier — single fast LLM call to decide swarm vs solo."""
        try:
            resp = await self.router.complete(
                LLMRequest(
                    user=(
                        "Decide if this user message needs multiple parallel "
                        "expert agents (book restaurant, build app, research "
                        "across many sources, etc.) or just a single direct "
                        "answer. Reply with exactly one word: 'swarm' or 'solo'.\n\n"
                        f"Message: {text}"
                    ),
                    system="You are a fast routing classifier.",
                    task=TaskProfile.for_voice_turn(),
                    max_tokens=4,
                    temperature=0.0,
                )
            )
            return "swarm" in resp.text.lower()
        except Exception:
            return False

    # ------------------------------------------------------------------ voice
    async def transcribe(self, audio: bytes, *, mime: str = "audio/webm") -> str:
        return await self.stt.transcribe(audio, mime=mime)

    async def speak(self, text: str) -> bytes:
        return await self.tts.synthesize(text)

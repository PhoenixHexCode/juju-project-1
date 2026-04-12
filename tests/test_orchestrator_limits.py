"""Orchestrator depth and fanout enforcement test."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.agents.orchestrator import Orchestrator
from backend.llm.providers.base import (
    BaseLLMProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderCapabilities,
)
from backend.llm.router import LLMRouter


class ScriptedProvider(BaseLLMProvider):
    """Always returns a 'delegate one child' plan, so the agent tree wants to
    grow forever — the orchestrator must clamp it."""

    capabilities = ProviderCapabilities(
        name="scripted", default_model="m",
        reasoning=0.9, coding=0.9, long_context=0.9, speed=0.9,
        cost_efficiency=0.9, tools=0.9, vision=False, json_mode=True,
        max_context_tokens=128_000,
    )

    def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        # Synthesis prompts contain "Synthesize"; just answer them.
        if request.system and "synthesizing" in request.system:
            return CompletionResponse(text="final answer", provider="scripted", model="m")
        plan = {
            "decision": "delegate",
            "answer": "",
            "sub_agents": [
                {"name": "child", "expertise": "x", "goal": "g", "tools": []}
            ],
            "rationale": "always recurse",
        }
        return CompletionResponse(text=json.dumps(plan), provider="scripted", model="m")


@pytest.mark.asyncio
async def test_orchestrator_caps_depth(monkeypatch):
    # Force tiny limits so the test runs fast.
    monkeypatch.setenv("AGENT_MAX_PARALLEL", "2")
    monkeypatch.setenv("AGENT_MAX_DEPTH", "2")
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "30")
    from backend import config as cfg
    cfg.get_settings.cache_clear()

    router = LLMRouter(providers=[ScriptedProvider()])
    orch = Orchestrator(router=router)
    report = await orch.handle_request("test goal")

    assert report.total_agents_spawned >= 1
    # Cannot have spawned an unbounded number — global cap is parallel * (depth+1).
    assert report.total_agents_spawned <= 2 * (2 + 1)
    assert report.final_answer  # produced *something*

"""Tests for the LLM router's scoring + fallthrough logic.

Uses fake providers so the suite runs offline with zero API keys.
"""
from __future__ import annotations

import asyncio
from typing import List

import pytest

from backend.llm.providers.base import (
    BaseLLMProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderCapabilities,
    ProviderUnavailable,
)
from backend.llm.router import LLMRequest, LLMRouter, TaskProfile


class FakeProvider(BaseLLMProvider):
    def __init__(self, caps: ProviderCapabilities, fail: bool = False):
        self.capabilities = caps
        self.fail = fail
        self.calls = 0

    def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.calls += 1
        if self.fail:
            raise RuntimeError("kaboom")
        return CompletionResponse(
            text=f"hi from {self.capabilities.name}",
            provider=self.capabilities.name,
            model=self.capabilities.default_model,
        )


def make_caps(name: str, **overrides) -> ProviderCapabilities:
    base = dict(
        name=name, default_model=f"{name}-model",
        reasoning=0.5, coding=0.5, long_context=0.5, speed=0.5,
        cost_efficiency=0.5, tools=0.5, vision=False, json_mode=True,
        max_context_tokens=128_000,
    )
    base.update(overrides)
    return ProviderCapabilities(**base)


@pytest.mark.asyncio
async def test_router_picks_fastest_for_voice_turn():
    fast = FakeProvider(make_caps("fast", speed=0.99, reasoning=0.7))
    slow = FakeProvider(make_caps("slow", speed=0.4, reasoning=0.99))
    router = LLMRouter(providers=[slow, fast])
    resp = await router.complete(LLMRequest(user="hi", task=TaskProfile.for_voice_turn()))
    assert resp.provider == "fast"


@pytest.mark.asyncio
async def test_router_picks_smartest_for_deep_reasoning():
    fast = FakeProvider(make_caps("fast", speed=0.99, reasoning=0.5))
    smart = FakeProvider(make_caps("smart", speed=0.4, reasoning=0.99))
    router = LLMRouter(providers=[fast, smart])
    resp = await router.complete(LLMRequest(user="hi", task=TaskProfile.for_deep_reasoning()))
    assert resp.provider == "smart"


@pytest.mark.asyncio
async def test_router_skips_provider_lacking_long_context():
    short = FakeProvider(make_caps("short", long_context=0.99, max_context_tokens=8_000))
    long = FakeProvider(make_caps("long", long_context=0.8, max_context_tokens=2_000_000))
    router = LLMRouter(providers=[short, long])
    resp = await router.complete(
        LLMRequest(user="hi", task=TaskProfile.for_long_doc(tokens=500_000))
    )
    assert resp.provider == "long"


@pytest.mark.asyncio
async def test_router_falls_through_on_failure():
    bad = FakeProvider(make_caps("bad", reasoning=0.99), fail=True)
    good = FakeProvider(make_caps("good", reasoning=0.95))
    router = LLMRouter(providers=[bad, good])
    resp = await router.complete(LLMRequest(user="hi"))
    assert resp.provider == "good"
    assert bad.calls == 1
    assert good.calls == 1


@pytest.mark.asyncio
async def test_router_no_providers_raises():
    router = LLMRouter(providers=[])
    with pytest.raises(ProviderUnavailable):
        await router.complete(LLMRequest(user="hi"))

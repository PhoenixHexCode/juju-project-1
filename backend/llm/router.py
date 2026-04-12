"""LLM-agnostic router.

Picks the best available provider for each request based on a TaskProfile,
the providers' static capabilities, and the user's preference order. Falls
through to the next-best option on failure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..config import get_settings
from .providers import (
    AnthropicProvider,
    BaseLLMProvider,
    GoogleProvider,
    GroqProvider,
    MistralProvider,
    OpenAIProvider,
    ProviderUnavailable,
)
from .providers.base import CompletionRequest, CompletionResponse, Message

log = logging.getLogger(__name__)


@dataclass
class TaskProfile:
    """How the caller describes what kind of task this is.

    Each weight is 0..1; the router multiplies them by the corresponding
    capability score to compute a fitness number per provider.
    """

    needs_reasoning: float = 0.5
    needs_coding: float = 0.0
    needs_long_context: float = 0.0
    needs_speed: float = 0.3            # voice turns crank this up
    needs_cost_efficiency: float = 0.2
    needs_tools: float = 0.0
    needs_vision: bool = False
    needs_json: bool = False
    estimated_input_tokens: int = 1000

    @classmethod
    def for_voice_turn(cls) -> "TaskProfile":
        return cls(needs_reasoning=0.4, needs_speed=0.95, needs_cost_efficiency=0.4)

    @classmethod
    def for_deep_reasoning(cls) -> "TaskProfile":
        return cls(needs_reasoning=0.99, needs_speed=0.1)

    @classmethod
    def for_coding(cls) -> "TaskProfile":
        return cls(needs_coding=0.99, needs_reasoning=0.7, needs_long_context=0.6)

    @classmethod
    def for_long_doc(cls, tokens: int) -> "TaskProfile":
        return cls(
            needs_long_context=0.99,
            needs_reasoning=0.6,
            estimated_input_tokens=tokens,
        )


@dataclass
class LLMRequest:
    user: str
    system: Optional[str] = None
    history: List[Message] = field(default_factory=list)
    task: TaskProfile = field(default_factory=TaskProfile)
    max_tokens: int = 1024
    temperature: float = 0.7
    json_mode: bool = False
    force_provider: Optional[str] = None  # bypass scoring


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    score: float
    usage: Dict[str, int] = field(default_factory=dict)


class LLMRouter:
    """Holds all configured providers and chooses the best one per call."""

    def __init__(self, providers: Optional[List[BaseLLMProvider]] = None):
        settings = get_settings()
        if providers is None:
            providers = [
                AnthropicProvider(settings.anthropic_api_key),
                OpenAIProvider(settings.openai_api_key),
                GoogleProvider(settings.google_api_key),
                GroqProvider(settings.groq_api_key),
                MistralProvider(settings.mistral_api_key),
            ]
        self._providers: Dict[str, BaseLLMProvider] = {
            p.capabilities.name: p for p in providers if p.is_available()
        }
        self._preference = settings.llm_preference_list
        if not self._providers:
            log.warning(
                "LLMRouter initialized with NO available providers. "
                "Set at least one *_API_KEY in your .env."
            )

    @property
    def available_providers(self) -> List[str]:
        return list(self._providers.keys())

    # ------------------------------------------------------------------ scoring
    def _score(self, provider: BaseLLMProvider, task: TaskProfile) -> float:
        c = provider.capabilities
        if task.needs_vision and not c.vision:
            return -1.0
        if task.needs_json and not c.json_mode:
            return -1.0
        if task.estimated_input_tokens > c.max_context_tokens:
            return -1.0

        score = (
            c.reasoning * task.needs_reasoning
            + c.coding * task.needs_coding
            + c.long_context * task.needs_long_context
            + c.speed * task.needs_speed
            + c.cost_efficiency * task.needs_cost_efficiency
            + c.tools * task.needs_tools
        )
        # Tiny preference-order tiebreaker
        if c.name in self._preference:
            score += 0.01 * (len(self._preference) - self._preference.index(c.name))
        return score

    def rank(self, task: TaskProfile) -> List[tuple[BaseLLMProvider, float]]:
        ranked = [
            (p, self._score(p, task)) for p in self._providers.values()
        ]
        ranked = [r for r in ranked if r[1] >= 0]
        ranked.sort(key=lambda r: r[1], reverse=True)
        return ranked

    # ------------------------------------------------------------------- public
    async def complete(self, req: LLMRequest) -> LLMResponse:
        if not self._providers:
            raise ProviderUnavailable(
                "No LLM providers configured. Set at least one API key."
            )

        if req.force_provider:
            provider = self._providers.get(req.force_provider)
            if not provider:
                raise ProviderUnavailable(
                    f"Forced provider '{req.force_provider}' is not available. "
                    f"Available: {self.available_providers}"
                )
            ranked = [(provider, 0.0)]
        else:
            ranked = self.rank(req.task)

        if not ranked:
            raise ProviderUnavailable(
                "No provider matched the task profile (vision/json/context constraints)."
            )

        last_err: Exception | None = None
        for provider, score in ranked:
            try:
                comp_req = CompletionRequest(
                    messages=[*req.history, Message("user", req.user)],
                    system=req.system,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                    json_mode=req.json_mode,
                )
                resp: CompletionResponse = await provider.complete(comp_req)
                return LLMResponse(
                    text=resp.text,
                    provider=resp.provider,
                    model=resp.model,
                    score=score,
                    usage=resp.usage,
                )
            except Exception as e:
                log.warning(
                    "Provider %s failed (%s); falling through.", provider.capabilities.name, e
                )
                last_err = e
                continue

        raise ProviderUnavailable(f"All providers failed. Last error: {last_err}")

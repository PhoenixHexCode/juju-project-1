"""Base interface every LLM provider adapter implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ProviderUnavailable(Exception):
    """Raised when a provider has no API key or its SDK is not importable."""


@dataclass
class ProviderCapabilities:
    """Static metadata about what a provider/model can do.

    The router uses these to score providers against an incoming task profile.
    Numbers are 0..1 quality estimates, intentionally rough.
    """

    name: str
    default_model: str
    reasoning: float          # complex multi-step reasoning quality
    coding: float             # code generation quality
    long_context: float       # handles large inputs well
    speed: float              # tokens/sec, higher = faster
    cost_efficiency: float    # higher = cheaper
    tools: float              # tool / function calling reliability
    vision: bool = False
    json_mode: bool = True
    max_context_tokens: int = 128_000


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class CompletionRequest:
    messages: List[Message]
    system: Optional[str] = None
    max_tokens: int = 1024
    temperature: float = 0.7
    json_mode: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResponse:
    text: str
    provider: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    raw: Any = None


class BaseLLMProvider(ABC):
    """All providers expose the same async `complete()` interface."""

    capabilities: ProviderCapabilities

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    @abstractmethod
    def is_available(self) -> bool: ...

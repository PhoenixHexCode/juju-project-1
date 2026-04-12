"""Groq adapter (very fast inference for low-latency voice turns)."""
from __future__ import annotations

from .base import (
    BaseLLMProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderCapabilities,
    ProviderUnavailable,
)


class GroqProvider(BaseLLMProvider):
    capabilities = ProviderCapabilities(
        name="groq",
        default_model="llama-3.3-70b-versatile",
        reasoning=0.85,
        coding=0.83,
        long_context=0.75,
        speed=0.99,                # Groq's headline feature
        cost_efficiency=0.85,
        tools=0.80,
        vision=False,
        json_mode=True,
        max_context_tokens=128_000,
    )

    def __init__(self, api_key: str | None):
        self._client = None
        if api_key:
            try:
                from groq import AsyncGroq
                self._client = AsyncGroq(api_key=api_key)
            except ImportError:
                self._client = None

    def is_available(self) -> bool:
        return self._client is not None

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._client:
            raise ProviderUnavailable("Groq client not configured")

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        resp = await self._client.chat.completions.create(
            model=request.extra.get("model", self.capabilities.default_model),
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        return CompletionResponse(
            text=resp.choices[0].message.content or "",
            provider=self.capabilities.name,
            model=resp.model,
            usage={
                "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
            },
            raw=resp,
        )

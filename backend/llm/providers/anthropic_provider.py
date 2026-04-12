"""Anthropic Claude adapter."""
from __future__ import annotations

from .base import (
    BaseLLMProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderCapabilities,
    ProviderUnavailable,
)


class AnthropicProvider(BaseLLMProvider):
    capabilities = ProviderCapabilities(
        name="anthropic",
        default_model="claude-opus-4-6",
        reasoning=0.97,
        coding=0.96,
        long_context=0.95,
        speed=0.70,
        cost_efficiency=0.55,
        tools=0.95,
        vision=True,
        json_mode=True,
        max_context_tokens=200_000,
    )

    def __init__(self, api_key: str | None):
        self._api_key = api_key
        self._client = None
        if api_key:
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=api_key)
            except ImportError:
                self._client = None

    def is_available(self) -> bool:
        return self._client is not None

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._client:
            raise ProviderUnavailable("Anthropic client not configured")

        msgs = [
            {"role": m.role, "content": m.content}
            for m in request.messages
            if m.role in ("user", "assistant")
        ]
        kwargs = {
            "model": request.extra.get("model", self.capabilities.default_model),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": msgs,
        }
        if request.system:
            kwargs["system"] = request.system

        resp = await self._client.messages.create(**kwargs)
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        return CompletionResponse(
            text=text,
            provider=self.capabilities.name,
            model=resp.model,
            usage={
                "input_tokens": getattr(resp.usage, "input_tokens", 0),
                "output_tokens": getattr(resp.usage, "output_tokens", 0),
            },
            raw=resp,
        )

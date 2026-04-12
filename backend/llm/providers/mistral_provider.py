"""Mistral adapter."""
from __future__ import annotations

from .base import (
    BaseLLMProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderCapabilities,
    ProviderUnavailable,
)


class MistralProvider(BaseLLMProvider):
    capabilities = ProviderCapabilities(
        name="mistral",
        default_model="mistral-large-latest",
        reasoning=0.88,
        coding=0.87,
        long_context=0.82,
        speed=0.82,
        cost_efficiency=0.78,
        tools=0.85,
        vision=False,
        json_mode=True,
        max_context_tokens=128_000,
    )

    def __init__(self, api_key: str | None):
        self._client = None
        if api_key:
            try:
                from mistralai import Mistral
                self._client = Mistral(api_key=api_key)
            except ImportError:
                self._client = None

    def is_available(self) -> bool:
        return self._client is not None

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._client:
            raise ProviderUnavailable("Mistral client not configured")

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        resp = await self._client.chat.complete_async(
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

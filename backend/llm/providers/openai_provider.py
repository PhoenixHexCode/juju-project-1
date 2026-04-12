"""OpenAI GPT adapter."""
from __future__ import annotations

from .base import (
    BaseLLMProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderCapabilities,
    ProviderUnavailable,
)


class OpenAIProvider(BaseLLMProvider):
    capabilities = ProviderCapabilities(
        name="openai",
        default_model="gpt-4o",
        reasoning=0.94,
        coding=0.93,
        long_context=0.85,
        speed=0.80,
        cost_efficiency=0.60,
        tools=0.96,
        vision=True,
        json_mode=True,
        max_context_tokens=128_000,
    )

    def __init__(self, api_key: str | None):
        self._client = None
        if api_key:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=api_key)
            except ImportError:
                self._client = None

    def is_available(self) -> bool:
        return self._client is not None

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._client:
            raise ProviderUnavailable("OpenAI client not configured")

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        kwargs = {
            "model": request.extra.get("model", self.capabilities.default_model),
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        return CompletionResponse(
            text=choice.message.content or "",
            provider=self.capabilities.name,
            model=resp.model,
            usage={
                "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
            },
            raw=resp,
        )

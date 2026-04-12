"""Google Gemini adapter."""
from __future__ import annotations

import asyncio

from .base import (
    BaseLLMProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderCapabilities,
    ProviderUnavailable,
)


class GoogleProvider(BaseLLMProvider):
    capabilities = ProviderCapabilities(
        name="google",
        default_model="gemini-1.5-pro",
        reasoning=0.91,
        coding=0.88,
        long_context=0.99,        # Gemini's headline strength
        speed=0.78,
        cost_efficiency=0.70,
        tools=0.85,
        vision=True,
        json_mode=True,
        max_context_tokens=2_000_000,
    )

    def __init__(self, api_key: str | None):
        self._api_key = api_key
        self._genai = None
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._genai = genai
            except ImportError:
                self._genai = None

    def is_available(self) -> bool:
        return self._genai is not None

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._genai:
            raise ProviderUnavailable("Google client not configured")

        model_name = request.extra.get("model", self.capabilities.default_model)
        model = self._genai.GenerativeModel(
            model_name,
            system_instruction=request.system,
        )
        history = [
            {"role": "user" if m.role == "user" else "model", "parts": [m.content]}
            for m in request.messages
        ]
        # Gemini SDK is sync; offload to a thread.
        resp = await asyncio.to_thread(
            model.generate_content,
            history,
            generation_config={
                "max_output_tokens": request.max_tokens,
                "temperature": request.temperature,
            },
        )
        return CompletionResponse(
            text=resp.text or "",
            provider=self.capabilities.name,
            model=model_name,
            usage={},
            raw=resp,
        )

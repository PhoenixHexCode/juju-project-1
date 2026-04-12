"""Text-to-speech using ElevenLabs.

The voice ID is taken from settings.elevenlabs_voice_id. If you leave it blank,
we use a built-in preset. NEVER use a voice clone of a real person without
their explicit consent.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

from ..config import get_settings

log = logging.getLogger(__name__)

# Built-in ElevenLabs preset voice that ships with every account.
DEFAULT_PRESET_VOICE_ID = "ErXwobaYiN019PkySvjV"  # "Antoni"


class TextToSpeech:
    def __init__(self):
        self._settings = get_settings()
        self._client = None
        if self._settings.elevenlabs_api_key:
            try:
                from elevenlabs.client import ElevenLabs
                self._client = ElevenLabs(api_key=self._settings.elevenlabs_api_key)
            except ImportError:
                log.warning("elevenlabs SDK not installed; TTS disabled.")

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def voice_id(self) -> str:
        return self._settings.elevenlabs_voice_id or DEFAULT_PRESET_VOICE_ID

    async def synthesize(self, text: str) -> bytes:
        """Return raw mp3 bytes for the spoken `text`."""
        if not self._client:
            raise RuntimeError(
                "TTS unavailable. Set ELEVENLABS_API_KEY in your .env."
            )
        return await asyncio.to_thread(self._sync_synthesize, text)

    def _sync_synthesize(self, text: str) -> bytes:
        audio_iter = self._client.text_to_speech.convert(
            voice_id=self.voice_id,
            model_id="eleven_turbo_v2_5",
            output_format="mp3_44100_128",
            text=text,
        )
        return b"".join(audio_iter)

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        """Yield mp3 chunks as they're produced (lower TTFB on long replies)."""
        if not self._client:
            raise RuntimeError("TTS unavailable. Set ELEVENLABS_API_KEY.")
        loop = asyncio.get_running_loop()
        chunks = await loop.run_in_executor(None, self._collect_chunks, text)
        for c in chunks:
            yield c

    def _collect_chunks(self, text: str) -> list[bytes]:
        return list(
            self._client.text_to_speech.convert_as_stream(
                voice_id=self.voice_id,
                model_id="eleven_turbo_v2_5",
                output_format="mp3_44100_128",
                text=text,
            )
        )

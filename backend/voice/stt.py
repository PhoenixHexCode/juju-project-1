"""Speech-to-text.

Two paths:
 1. Local faster-whisper (no cloud, runs on CPU/GPU, default).
 2. OpenAI Whisper API if OPENAI_API_KEY is configured and local model isn't.

Both expose a single async `transcribe(audio_bytes)` method that returns text.
"""
from __future__ import annotations

import asyncio
import io
import logging
import tempfile
from pathlib import Path
from typing import Optional

from ..config import get_settings

log = logging.getLogger(__name__)


class SpeechToText:
    def __init__(self, model_size: Optional[str] = None):
        self._settings = get_settings()
        self._model_size = model_size or self._settings.whisper_model
        self._local_model = None
        self._openai = None

        # Try local first (offline-friendly)
        try:
            from faster_whisper import WhisperModel
            self._local_model = WhisperModel(
                self._model_size, device="auto", compute_type="auto"
            )
            log.info("STT using local faster-whisper '%s'", self._model_size)
        except Exception as e:
            log.info("Local faster-whisper unavailable (%s); will try OpenAI.", e)

        if self._local_model is None and self._settings.openai_api_key:
            try:
                from openai import AsyncOpenAI
                self._openai = AsyncOpenAI(api_key=self._settings.openai_api_key)
                log.info("STT using OpenAI Whisper API")
            except ImportError:
                self._openai = None

    @property
    def available(self) -> bool:
        return self._local_model is not None or self._openai is not None

    async def transcribe(self, audio_bytes: bytes, *, mime: str = "audio/webm") -> str:
        if self._local_model is not None:
            return await asyncio.to_thread(self._local_transcribe, audio_bytes)
        if self._openai is not None:
            return await self._openai_transcribe(audio_bytes, mime)
        raise RuntimeError("No STT backend available. Install faster-whisper or set OPENAI_API_KEY.")

    # ------------------------------------------------------------------ helpers
    def _local_transcribe(self, audio_bytes: bytes) -> str:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as f:
            f.write(audio_bytes)
            f.flush()
            segments, _ = self._local_model.transcribe(f.name, beam_size=1)
            return " ".join(seg.text.strip() for seg in segments).strip()

    async def _openai_transcribe(self, audio_bytes: bytes, mime: str) -> str:
        suffix = ".webm" if "webm" in mime else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        try:
            with open(path, "rb") as fh:
                resp = await self._openai.audio.transcriptions.create(
                    model="whisper-1", file=fh
                )
            return resp.text or ""
        finally:
            Path(path).unlink(missing_ok=True)

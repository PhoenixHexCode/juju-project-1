"""Centralized settings, loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret: str = "change-me"
    allowed_origins: str = "http://localhost:8000"

    # LLM keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None

    llm_preference_order: str = "anthropic,openai,google,groq,mistral"
    llm_max_tokens: int = 4096

    # Voice
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    whisper_model: str = "base"

    # Memory
    memory_db_path: str = "./data/companion.db"
    chroma_path: str = "./data/chroma"

    # Agents
    agent_max_parallel: int = 5
    agent_max_depth: int = 3
    agent_timeout_seconds: int = 120

    # Telephony
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_from_number: Optional[str] = None

    # Host bridge
    host_bridge_url: Optional[str] = None
    host_bridge_token: Optional[str] = None

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def llm_preference_list(self) -> List[str]:
        return [p.strip() for p in self.llm_preference_order.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

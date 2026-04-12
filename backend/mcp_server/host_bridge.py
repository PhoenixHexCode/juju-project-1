"""Client for the user's home-computer "host bridge".

The host bridge is a tiny FastAPI process you run on your home machine. The
companion connects to it (over a token-authenticated HTTPS endpoint) to do
things like: open files, run builds, launch a Vite dev server, etc.

A reference host bridge implementation lives in `tools/host_bridge_server.py`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)


class HostBridgeClient:
    def __init__(self, url: Optional[str], token: Optional[str]):
        self.url = url
        self.token = token

    @classmethod
    def from_env(cls) -> "HostBridgeClient":
        s = get_settings()
        return cls(url=s.host_bridge_url, token=s.host_bridge_token)

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token)

    async def call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.configured:
            return {"ok": False, "error": "host bridge not configured"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.url.rstrip('/')}/action/{action}",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
            )
            resp.raise_for_status()
            return resp.json()

"""App-builder skill — drives a remote dev box via the host bridge.

When the user says "build me a small web app that does X", an orchestrator
agent will:
  1. Spawn a planning sub-agent (specs the app, picks a stack).
  2. Spawn a coding sub-agent that calls AppBuilderSkill.scaffold() to drop
     files on the home computer through the host bridge.
  3. Spawn a test sub-agent that runs the test suite via host_bridge_call.
  4. Spawn a runtime sub-agent that boots the dev server and returns its URL.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from ..mcp_server.host_bridge import HostBridgeClient

log = logging.getLogger(__name__)


@dataclass
class FileSpec:
    path: str
    content: str


class AppBuilderSkill:
    def __init__(self, bridge: HostBridgeClient | None = None):
        self.bridge = bridge or HostBridgeClient.from_env()

    @property
    def configured(self) -> bool:
        return self.bridge.configured

    async def scaffold(self, project_dir: str, files: List[FileSpec]) -> Dict[str, Any]:
        if not self.configured:
            return {"ok": False, "error": "host bridge not configured"}
        return await self.bridge.call(
            "scaffold",
            {
                "project_dir": project_dir,
                "files": [{"path": f.path, "content": f.content} for f in files],
            },
        )

    async def install(self, project_dir: str, manager: str = "npm") -> Dict[str, Any]:
        return await self.bridge.call(
            "shell",
            {"cwd": project_dir, "command": f"{manager} install"},
        )

    async def test(self, project_dir: str, manager: str = "npm") -> Dict[str, Any]:
        return await self.bridge.call(
            "shell",
            {"cwd": project_dir, "command": f"{manager} test --silent"},
        )

    async def serve(self, project_dir: str, manager: str = "npm") -> Dict[str, Any]:
        return await self.bridge.call(
            "serve",
            {"cwd": project_dir, "command": f"{manager} run dev"},
        )

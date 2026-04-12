"""Embedded MCP server exposing device tools to the companion.

This module builds an MCP server in-process. Tools are registered conditionally
based on the detected device kind. The companion's agents call these tools via
the MCP protocol — the same way Claude Desktop or any other MCP client would.

Tools provided:
  - fs_read(path)              read a local file
  - fs_write(path, content)    write a local file (perm-gated)
  - shell_run(command)         run a shell command (perm-gated)
  - process_list()             list running processes
  - browser_open(url)          open a URL on the user's desktop (desktop only)
  - host_bridge_call(...)      proxy a call to the user's home computer

If the `mcp` SDK isn't installed, this module falls back to a plain function
registry that the agents can still call directly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import webbrowser
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..security.permissions import PermissionBroker, PermissionDenied
from .device import DeviceInfo, detect_device
from .host_bridge import HostBridgeClient

log = logging.getLogger(__name__)

ToolFn = Callable[..., Awaitable[Any]]


@dataclass
class ToolDescriptor:
    name: str
    description: str
    fn: ToolFn


class ToolRegistry:
    """Plain in-process tool registry that mirrors MCP semantics."""

    def __init__(self):
        self._tools: Dict[str, ToolDescriptor] = {}

    def register(self, name: str, description: str, fn: ToolFn) -> None:
        self._tools[name] = ToolDescriptor(name=name, description=description, fn=fn)

    def list(self) -> List[Dict[str, str]]:
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    async def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return await self._tools[name].fn(**kwargs)


# ---------------------------------------------------------------------- builder
def build_mcp_server(
    permissions: Optional[PermissionBroker] = None,
    host_bridge: Optional[HostBridgeClient] = None,
) -> ToolRegistry:
    device = detect_device()
    perms = permissions or PermissionBroker()
    bridge = host_bridge or HostBridgeClient.from_env()
    registry = ToolRegistry()

    # ---- filesystem ---------------------------------------------------------
    async def fs_read(path: str) -> str:
        await perms.require("fs.read", resource=path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()

    async def fs_write(path: str, content: str) -> Dict[str, Any]:
        await perms.require("fs.write", resource=path)
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return {"ok": True, "bytes": len(content)}

    # ---- shell --------------------------------------------------------------
    async def shell_run(command: str, timeout: int = 30) -> Dict[str, Any]:
        await perms.require("shell.run", resource=command)
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"ok": False, "error": "timeout"}
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "stdout": stdout.decode("utf-8", "replace"),
            "stderr": stderr.decode("utf-8", "replace"),
        }

    # ---- process list -------------------------------------------------------
    async def process_list() -> List[Dict[str, Any]]:
        try:
            import psutil
            return [
                {"pid": p.pid, "name": p.name()}
                for p in psutil.process_iter(attrs=["pid", "name"])
            ][:200]
        except ImportError:
            return [{"error": "psutil not installed"}]

    # ---- browser ------------------------------------------------------------
    async def browser_open(url: str) -> Dict[str, Any]:
        await perms.require("browser.open", resource=url)
        webbrowser.open(url)
        return {"ok": True}

    # ---- remote host bridge -------------------------------------------------
    async def host_bridge_call(action: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        await perms.require("host.remote", resource=action)
        if not bridge.configured:
            return {"ok": False, "error": "host bridge URL not configured"}
        return await bridge.call(action, payload or {})

    # ---- registration -------------------------------------------------------
    registry.register("fs_read", "Read a local file by path.", fs_read)
    registry.register(
        "fs_write", "Write content to a local file (creates dirs).", fs_write
    )
    registry.register(
        "shell_run", "Run a shell command and return stdout/stderr.", shell_run
    )
    registry.register("process_list", "List running processes.", process_list)

    if "browser.open" in device.capabilities:
        registry.register(
            "browser_open", "Open a URL in the user's default browser.", browser_open
        )

    registry.register(
        "host_bridge_call",
        "Proxy a request to the user's home computer via the secure host bridge.",
        host_bridge_call,
    )

    log.info(
        "MCP tools registered for device=%s: %s",
        device.kind,
        [t["name"] for t in registry.list()],
    )
    return registry


def list_tools(registry: ToolRegistry) -> List[Dict[str, str]]:
    return registry.list()

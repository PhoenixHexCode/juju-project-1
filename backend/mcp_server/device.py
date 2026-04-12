"""Detect what kind of device the companion is currently running on.

The MCP server uses this to expose only the tools that make sense for the host.
"""
from __future__ import annotations

import os
import platform
import socket
import sys
from dataclasses import dataclass, field
from typing import List


@dataclass
class DeviceInfo:
    kind: str             # "desktop" | "server" | "phone-pwa" | "unknown"
    os: str
    arch: str
    hostname: str
    python_version: str
    capabilities: List[str] = field(default_factory=list)


def detect_device() -> DeviceInfo:
    sysname = platform.system().lower()
    if "android" in sysname or "iphone" in sysname or "ios" in sysname:
        kind = "phone-native"
    elif sysname in ("linux", "darwin", "windows"):
        # Server vs desktop heuristic: presence of a display environment.
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or sysname == "darwin" or sysname == "windows":
            kind = "desktop"
        else:
            kind = "server"
    else:
        kind = "unknown"

    caps: List[str] = ["fs.read", "fs.write", "shell.run", "process.list"]
    if kind == "desktop":
        caps += ["browser.open", "clipboard", "notifications"]
    if kind in ("desktop", "server"):
        caps += ["network.fetch", "git"]

    return DeviceInfo(
        kind=kind,
        os=sysname,
        arch=platform.machine(),
        hostname=socket.gethostname(),
        python_version=sys.version.split()[0],
        capabilities=caps,
    )

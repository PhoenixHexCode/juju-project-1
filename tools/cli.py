"""Headless CLI client — talk to the companion from a terminal.

Useful for SSHing into the box that runs the companion when you don't have a
browser. Reads from stdin / writes to stdout, no audio.
"""
from __future__ import annotations

import asyncio
import os
import sys

# Make `backend` importable when this script is run directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.companion import Companion  # noqa: E402


async def main():
    companion = Companion()
    user = os.environ.get("JUJU_USER", "cli-user")
    print(
        f"JUJU online — providers={companion.router.available_providers} "
        f"device={companion.device.kind}",
        file=sys.stderr,
    )
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        reply = await companion.chat(user, line)
        tag = "[agents]" if reply.used_agents else f"[{reply.provider}/{reply.model}]"
        print(f"{tag} {reply.text}\n")


if __name__ == "__main__":
    asyncio.run(main())

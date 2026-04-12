"""Reference Host Bridge server — run this on your HOME computer.

This is the small, locked-down service the companion talks to when it needs
to do something on your personal machine (read files, scaffold projects, run
the dev server). It is intentionally minimal and bearer-token authenticated.

Usage on your home machine:
    pip install fastapi uvicorn
    export HOST_BRIDGE_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
    python -m tools.host_bridge_server

Then in your companion .env, point at it:
    HOST_BRIDGE_URL=https://my-home-pc.example.com:9090
    HOST_BRIDGE_TOKEN=<the same token>

Security notes:
  - Run behind HTTPS (Caddy / Cloudflare Tunnel / Tailscale Funnel).
  - The token is the only credential — rotate it if it leaks.
  - All `shell` actions run inside ALLOWED_ROOT only. Adjust to taste.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException

TOKEN = os.environ.get("HOST_BRIDGE_TOKEN")
ALLOWED_ROOT = Path(os.environ.get("HOST_BRIDGE_ROOT", str(Path.home() / "companion-projects"))).resolve()
ALLOWED_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Host Bridge")


def auth(authorization: str | None) -> None:
    if not TOKEN:
        raise HTTPException(500, "HOST_BRIDGE_TOKEN not set on the host")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer")
    if authorization.split(None, 1)[1] != TOKEN:
        raise HTTPException(401, "bad token")


def safe_path(p: str) -> Path:
    out = (ALLOWED_ROOT / p).resolve()
    if not str(out).startswith(str(ALLOWED_ROOT)):
        raise HTTPException(400, "path escapes allowed root")
    return out


@app.post("/action/scaffold")
async def scaffold(payload: dict = Body(...), authorization: str | None = Header(None)):
    auth(authorization)
    project_dir = safe_path(payload["project_dir"])
    project_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for f in payload.get("files", []):
        p = safe_path(os.path.join(payload["project_dir"], f["path"]))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f["content"])
        written.append(str(p.relative_to(ALLOWED_ROOT)))
    return {"ok": True, "files": written, "project_dir": str(project_dir.relative_to(ALLOWED_ROOT))}


@app.post("/action/shell")
async def shell(payload: dict = Body(...), authorization: str | None = Header(None)):
    auth(authorization)
    cwd = safe_path(payload["cwd"])
    result = subprocess.run(
        payload["command"],
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return {
        "ok": result.returncode == 0,
        "code": result.returncode,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-8000:],
    }


@app.post("/action/serve")
async def serve(payload: dict = Body(...), authorization: str | None = Header(None)):
    auth(authorization)
    cwd = safe_path(payload["cwd"])
    # Background process — record the pid for later teardown.
    proc = subprocess.Popen(
        payload["command"],
        cwd=str(cwd),
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"ok": True, "pid": proc.pid, "cwd": str(cwd)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("HOST_BRIDGE_PORT", "9090")))

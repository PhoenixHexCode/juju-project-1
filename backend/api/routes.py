"""REST + WebSocket routes for the companion."""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response

from ..companion import Companion
from ..security.auth import create_token, verify_token

log = logging.getLogger(__name__)

router = APIRouter()


def get_companion(request: Request) -> Companion:
    return request.app.state.companion


# ------------------------------------------------------------------------ auth
@router.post("/auth/login")
async def login(payload: Dict[str, str] = Body(...)):
    """Demo auth: any non-empty username gets a token. Replace with real
    user lookup before exposing this on the open internet."""
    username = (payload.get("username") or "").strip()
    if not username:
        raise HTTPException(400, "username required")
    return {"token": create_token(username), "user": username}


def require_user(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    payload = verify_token(auth.split(None, 1)[1])
    if not payload:
        raise HTTPException(401, "invalid token")
    return payload.get("sub", "anon")


# ------------------------------------------------------------------------ chat
@router.post("/chat")
async def chat(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    user: str = Depends(require_user),
):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    voice_mode = bool(payload.get("voice_mode"))
    companion = get_companion(request)
    reply = await companion.chat(user, text, voice_mode=voice_mode)
    return {
        "text": reply.text,
        "provider": reply.provider,
        "model": reply.model,
        "used_agents": reply.used_agents,
        "agents_spawned": (
            reply.agent_report.total_agents_spawned if reply.agent_report else 0
        ),
    }


# -------------------------------------------------------------------- memory
@router.get("/memory/recent")
async def memory_recent(
    request: Request,
    limit: int = 20,
    user: str = Depends(require_user),
):
    items = get_companion(request).memory.recent(user, limit=limit)
    return [
        {"id": i.id, "role": i.role, "kind": i.kind, "content": i.content}
        for i in items
    ]


@router.get("/memory/search")
async def memory_search(
    request: Request,
    q: str,
    k: int = 5,
    user: str = Depends(require_user),
):
    items = get_companion(request).memory.search(user, q, k=k)
    return [
        {"id": i.id, "role": i.role, "kind": i.kind, "content": i.content}
        for i in items
    ]


# -------------------------------------------------------------------- tools
@router.get("/tools")
async def tools_list(request: Request, user: str = Depends(require_user)):
    return {
        "device": {
            "kind": get_companion(request).device.kind,
            "os": get_companion(request).device.os,
            "capabilities": get_companion(request).device.capabilities,
        },
        "tools": get_companion(request).tools.list(),
        "providers": get_companion(request).router.available_providers,
    }


# -------------------------------------------------------------------- voice
@router.post("/voice/transcribe")
async def voice_transcribe(
    request: Request,
    file: UploadFile,
    user: str = Depends(require_user),
):
    audio = await file.read()
    text = await get_companion(request).transcribe(
        audio, mime=file.content_type or "audio/webm"
    )
    return {"text": text}


@router.post("/voice/speak")
async def voice_speak(
    request: Request,
    payload: Dict[str, str] = Body(...),
    user: str = Depends(require_user),
):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    audio = await get_companion(request).speak(text)
    return Response(content=audio, media_type="audio/mpeg")


# -------------------------------------------------------------------- websocket
@router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket):
    """Bidirectional voice loop.

    Protocol (JSON over text frames):
      client -> server:
        {type: "auth", token: "..."}
        {type: "audio", mime: "audio/webm", data_b64: "..."}     # one user turn
        {type: "text",  text: "..."}                             # text-only turn
        {type: "permission_response", request_id, decision, scope, resource}
      server -> client:
        {type: "transcript", text}
        {type: "reply", text, provider, model}
        {type: "audio", mime: "audio/mpeg", data_b64}
        {type: "permission_request", id, scope, resource, options}
        {type: "error", error}
    """
    await ws.accept()
    companion: Companion = ws.app.state.companion
    user_id: Optional[str] = None
    perm_queue = companion.permissions.add_listener()

    async def pump_perms():
        try:
            while True:
                req = await perm_queue.get()
                await ws.send_json(
                    {
                        "type": "permission_request",
                        "id": req.id,
                        "scope": req.scope,
                        "resource": req.resource,
                        "options": req.options,
                    }
                )
        except Exception:
            pass

    perm_task = asyncio.create_task(pump_perms())

    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "auth":
                payload = verify_token(msg.get("token", ""))
                if not payload:
                    await ws.send_json({"type": "error", "error": "invalid token"})
                    await ws.close()
                    return
                user_id = payload.get("sub")
                await ws.send_json({"type": "ready", "user": user_id})
                continue

            if user_id is None:
                await ws.send_json({"type": "error", "error": "auth first"})
                continue

            if mtype == "permission_response":
                companion.permissions.resolve(
                    request_id=msg["request_id"],
                    decision=msg["decision"],
                    scope=msg["scope"],
                    resource=msg.get("resource"),
                )
                continue

            if mtype == "audio":
                audio = base64.b64decode(msg["data_b64"])
                text = await companion.transcribe(audio, mime=msg.get("mime", "audio/webm"))
                await ws.send_json({"type": "transcript", "text": text})
            elif mtype == "text":
                text = msg.get("text", "")
            else:
                await ws.send_json({"type": "error", "error": f"unknown type {mtype}"})
                continue

            if not text.strip():
                continue

            reply = await companion.chat(user_id, text, voice_mode=True)
            await ws.send_json(
                {
                    "type": "reply",
                    "text": reply.text,
                    "provider": reply.provider,
                    "model": reply.model,
                    "used_agents": reply.used_agents,
                }
            )

            if companion.tts.available:
                try:
                    audio = await companion.speak(reply.text)
                    await ws.send_json(
                        {
                            "type": "audio",
                            "mime": "audio/mpeg",
                            "data_b64": base64.b64encode(audio).decode(),
                        }
                    )
                except Exception as e:
                    await ws.send_json({"type": "error", "error": f"tts: {e}"})

    except WebSocketDisconnect:
        pass
    finally:
        perm_task.cancel()
        companion.permissions.remove_listener(perm_queue)

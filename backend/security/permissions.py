"""Permission broker — voice-friendly elevation prompts.

When an agent or tool needs a capability the user hasn't granted yet, it raises
PermissionDenied. The API layer catches it, sends a `permission_request` event
down the WebSocket so the UI (or voice front-end) can ask the user to approve.

This is the central choke-point for "if you don't have permission, ask me via
voice with options".
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

log = logging.getLogger(__name__)


class PermissionDenied(Exception):
    def __init__(self, scope: str, resource: Optional[str] = None, options: Optional[List[str]] = None):
        self.scope = scope
        self.resource = resource
        self.options = options or [
            f"Allow once for this resource",
            f"Allow for the rest of this session",
            f"Always allow",
            f"Deny",
        ]
        super().__init__(f"Permission '{scope}' required for resource={resource}")


@dataclass
class PermissionRequest:
    id: str
    scope: str
    resource: Optional[str]
    options: List[str]


@dataclass
class GrantedPermission:
    scope: str
    resource: Optional[str] = None
    persistent: bool = False


class PermissionBroker:
    """In-memory permission state with pending-request future map.

    The voice/HTTP layer wires up `request_user()` to actually ask the user.
    Agents call `require()`, which either passes silently or escalates.
    """

    def __init__(self):
        self._granted_session: Set[tuple[str, Optional[str]]] = set()
        self._granted_persistent: Set[tuple[str, Optional[str]]] = set()
        self._pending: Dict[str, asyncio.Future[bool]] = {}
        self._listeners: List[asyncio.Queue[PermissionRequest]] = []

    # ---------------------- API surface for agents
    async def require(self, scope: str, *, resource: Optional[str] = None) -> None:
        key = (scope, resource)
        wildcard = (scope, None)
        if key in self._granted_session or key in self._granted_persistent:
            return
        if wildcard in self._granted_session or wildcard in self._granted_persistent:
            return
        # Need to ask
        ok = await self._ask_user(scope, resource)
        if not ok:
            raise PermissionDenied(scope=scope, resource=resource)

    # ---------------------- API surface for the UI
    def add_listener(self) -> asyncio.Queue[PermissionRequest]:
        q: asyncio.Queue[PermissionRequest] = asyncio.Queue()
        self._listeners.append(q)
        return q

    def remove_listener(self, q: asyncio.Queue) -> None:
        if q in self._listeners:
            self._listeners.remove(q)

    def resolve(self, request_id: str, decision: str, scope: str, resource: Optional[str]) -> None:
        """Called by the UI in response to a permission_request event."""
        decision = decision.lower()
        if decision in ("allow_once", "allow"):
            self._granted_session.add((scope, resource))
            ok = True
        elif decision == "allow_session":
            self._granted_session.add((scope, None))
            ok = True
        elif decision == "allow_always":
            self._granted_persistent.add((scope, None))
            ok = True
        else:
            ok = False
        fut = self._pending.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(ok)

    # ---------------------- internals
    async def _ask_user(self, scope: str, resource: Optional[str]) -> bool:
        if not self._listeners:
            log.warning(
                "Permission '%s' requested but no UI listener attached. Auto-denying.",
                scope,
            )
            return False
        req_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bool] = loop.create_future()
        self._pending[req_id] = fut
        request = PermissionRequest(
            id=req_id,
            scope=scope,
            resource=resource,
            options=["allow_once", "allow_session", "allow_always", "deny"],
        )
        for q in list(self._listeners):
            await q.put(request)
        try:
            return await asyncio.wait_for(fut, timeout=120)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            return False

"""Permission broker — grant flow + auto-deny when no listener."""
from __future__ import annotations

import asyncio

import pytest

from backend.security.permissions import PermissionBroker, PermissionDenied


@pytest.mark.asyncio
async def test_no_listener_denies():
    broker = PermissionBroker()
    with pytest.raises(PermissionDenied):
        await broker.require("fs.write", resource="/etc/passwd")


@pytest.mark.asyncio
async def test_listener_grant_flow():
    broker = PermissionBroker()
    queue = broker.add_listener()

    async def consumer():
        req = await queue.get()
        broker.resolve(req.id, "allow_once", req.scope, req.resource)

    consumer_task = asyncio.create_task(consumer())
    await broker.require("fs.read", resource="/tmp/x")
    await consumer_task

    # second call to same resource is silent
    await broker.require("fs.read", resource="/tmp/x")


@pytest.mark.asyncio
async def test_session_grant_covers_other_resources():
    broker = PermissionBroker()
    queue = broker.add_listener()

    async def consumer():
        req = await queue.get()
        broker.resolve(req.id, "allow_session", req.scope, req.resource)

    asyncio.create_task(consumer())
    await broker.require("shell.run", resource="ls")
    await broker.require("shell.run", resource="echo hi")  # different resource — still allowed

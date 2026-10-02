"""Smoke tests that need no external services."""

from __future__ import annotations

import httpx
import pytest

from app import __version__
from app.main import app


@pytest.mark.asyncio
async def test_liveness() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_reports_version_and_db() -> None:
    """Without a database, /v1/health returns 200 with db=ko and the version."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == __version__
    assert body["db"] == "ko"
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_compile_requires_a_task() -> None:
    """The compile route validates its body before doing any work."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/compile", json={})
    assert resp.status_code == 422  # missing `task`

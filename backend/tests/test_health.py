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
async def test_health_reports_version_and_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the database is unreachable, /v1/health returns 200 with db=ko + the version.

    Hermetic: the DB probe is forced to fail so the assertion holds whether or not a real
    database happens to be reachable (so the full suite can run under one command).
    """

    class _DownEngine:
        def connect(self) -> object:  # called inside the route's try/except → db="ko"
            raise RuntimeError("database unreachable (test)")

    monkeypatch.setattr("app.api.v1.routes.health.engine", _DownEngine())

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

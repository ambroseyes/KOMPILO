"""Smoke tests that need no external services."""

from __future__ import annotations

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_liveness() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_compile_stub_runs_all_stages() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/compile", json={"intent": "ship a feature"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_stub"] is True
    assert len(body["trace"]) == 8
    assert body["trace"][0]["stage"] == "understand"

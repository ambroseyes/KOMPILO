"""No-DB unit tests for the projects routes (auth gate, fail-closed)."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_projects_require_auth() -> None:
    """Without a token every project route is 401 — before any DB access."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/v1/projects", json={"slug": "p", "name": "P"})
        listed = await client.get("/v1/projects")
        fetched = await client.get(f"/v1/projects/{uuid.uuid4()}")
    assert created.status_code == 401
    assert listed.status_code == 401
    assert fetched.status_code == 401

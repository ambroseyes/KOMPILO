"""No-DB route tests for the V1.5 #1 endpoints: both are authenticated (fail-closed)."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_compare_requires_authentication() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/v1/prompts/{uuid.uuid4()}/versions/compare",
            json={"from_version": 1, "to_version": 2},
        )
    assert resp.status_code == 401  # before touching the DB or running any execution


@pytest.mark.asyncio
async def test_improve_loop_requires_authentication() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/improve/loop", json={"task": "x"})
    assert resp.status_code == 401

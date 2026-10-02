"""No-DB unit test for the execute route (auth gate)."""

from __future__ import annotations

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_execute_requires_auth() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/execute", json={"task": "do something"})
    assert resp.status_code == 401

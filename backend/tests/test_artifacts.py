"""No-DB unit tests for the artifacts routes (auth gate, fail-closed)."""
from __future__ import annotations

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_artifacts_require_tenant() -> None:
    """Without a tenant (no Bearer, no dev header) every route is 401 — before DB."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/artifacts", json={"name": "x"})
        listed = await client.get("/api/v1/artifacts")
    assert created.status_code == 401
    assert listed.status_code == 401

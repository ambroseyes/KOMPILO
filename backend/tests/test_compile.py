"""No-DB unit tests for the compile route (auth gate, fail-closed)."""

from __future__ import annotations

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_compile_requires_authentication() -> None:
    """Without a Bearer token (and no dev header) /compile is 401 — before any LLM call."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/compile", json={"intent": "ship a feature"})
    assert resp.status_code == 401

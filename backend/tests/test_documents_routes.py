"""No-DB route tests: every RAG corpus endpoint is authenticated (fail-closed)."""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_corpus_routes_require_authentication() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ingest = await client.post("/v1/documents", json={"title": "t", "content": "c"})
        search = await client.post("/v1/documents/search", json={"query": "q"})
        listing = await client.get("/v1/documents")
        get_one = await client.get(f"/v1/documents/{uuid.uuid4()}")
    # All fail closed before touching the DB or embedding anything.
    assert ingest.status_code == 401
    assert search.status_code == 401
    assert listing.status_code == 401
    assert get_one.status_code == 401

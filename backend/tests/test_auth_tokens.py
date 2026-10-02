"""No-DB unit tests for token typing and auth-route validation.

These never touch the database: validation errors and token-type rejections all fire
before any DB access.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.security import create_access_token, create_refresh_token
from app.main import app


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_signup_validates_body() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/auth/signup", json={"org_slug": "acme"})
    assert resp.status_code == 422  # missing org_name/email/password


@pytest.mark.asyncio
async def test_refresh_validates_body() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/auth/refresh", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_refresh_rejects_an_access_token() -> None:
    """An access token presented to /auth/refresh is rejected (type mismatch)."""
    access = create_access_token(subject="u", tenant_id="t", role="owner")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_is_not_accepted_as_api_bearer() -> None:
    """A refresh token must not grant API access (access-type required)."""
    refresh = create_refresh_token(subject="u", tenant_id="t", role="owner")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/projects", headers=_bearer(refresh))
    assert resp.status_code == 401

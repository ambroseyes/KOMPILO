"""Integration: SSE streaming of an execution (GET /v1/executions/{id}/stream).

Creates a real execution via /v1/execute (offline Echo STUB) then streams it over SSE,
asserting it receives step events, progressive token events, and a terminal done event.
Also checks auth (401 without a token) and tenant isolation (404 for an unknown id).
DISPOSABLE DB.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa

from app.core.tenancy import apply_tenant_guc
from app.db.session import engine, session_scope
from app.main import app
from app.models.organization import Organization


async def _db_reachable() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


async def _create_org(slug: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)
        s.add(Organization(id=org_id, slug=slug, name=slug))
    return org_id


async def _delete_org(org_id: uuid.UUID) -> None:
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)
        await s.execute(sa.delete(Organization).where(Organization.id == org_id))


async def _login(client: httpx.AsyncClient, slug: str) -> str:
    await client.post(
        "/v1/auth/register", json={"org_slug": slug, "email": "m@e.io", "password": "s3cret-pass"}
    )
    resp = await client.post(
        "/v1/auth/login", json={"org_slug": slug, "email": "m@e.io", "password": "s3cret-pass"}
    )
    return str(resp.json()["access_token"])


@pytest.mark.asyncio
async def test_execution_sse_stream() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug = f"sse-{suffix}"
    org = await _create_org(slug)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token = await _login(client, slug)
            bearer = {"Authorization": f"Bearer {token}"}

            created = await client.post(
                "/v1/execute",
                headers=bearer,
                json={"task": f"Rédige un message de bienvenue pour un client ({suffix})"},
            )
            assert created.status_code == 200, created.text
            execution_id = created.json()["execution_id"]
            assert execution_id, created.text  # PROCEED (executed), not a clarification ask

            # No token → 401 (EventSource can't send a header, so a token is required).
            assert (await client.get(f"/v1/executions/{execution_id}/stream")).status_code == 401
            # Unknown execution (valid token) → 404 (RLS/not found).
            unknown = await client.get(
                f"/v1/executions/{uuid.uuid4()}/stream", params={"token": token}
            )
            assert unknown.status_code == 404

            # Stream it: expect step → token(s) → done.
            body = ""
            async with client.stream(
                "GET", f"/v1/executions/{execution_id}/stream", params={"token": token}
            ) as resp:
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")
                async for chunk in resp.aiter_text():
                    body += chunk
                    if "event: done" in body:
                        break

            assert "event: step" in body
            assert "event: token" in body
            assert "event: done" in body
    finally:
        await _delete_org(org)

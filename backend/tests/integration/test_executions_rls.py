"""Integration: /compile persists a tenant-isolated Execution.

Proves that every /compile run writes an ``Execution`` row scoped to the caller's
tenant, that ``prompt_version_id`` is NULL for an ad-hoc intent (migration 0007),
and that RLS keeps one tenant's executions invisible to another.

Runs key-less: the default pipeline resolves ``EchoLLMClient`` in development, so
no ANTHROPIC_API_KEY is needed. Requires a migrated DB reachable as the app role;
skips otherwise. DISPOSABLE DB.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa

from app.core.tenancy import apply_tenant_guc
from app.db.session import engine, session_scope
from app.main import app
from app.models.execution import Execution
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
        await apply_tenant_guc(s, org_id)  # id == GUC so WITH CHECK passes
        s.add(Organization(id=org_id, slug=slug, name=slug))
    return org_id


async def _delete_org(org_id: uuid.UUID) -> None:
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)
        await s.execute(sa.delete(Organization).where(Organization.id == org_id))


async def _register_login(client: httpx.AsyncClient, slug: str, email: str) -> str:
    await client.post(
        "/v1/auth/register",
        json={"org_slug": slug, "email": email, "password": "s3cret-pass"},
    )
    resp = await client.post(
        "/v1/auth/login",
        json={"org_slug": slug, "email": email, "password": "s3cret-pass"},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _executions_for(org_id: uuid.UUID) -> list[Execution]:
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)  # RLS scopes the read to this tenant
        rows = (await s.execute(sa.select(Execution))).scalars().all()
        return list(rows)


@pytest.mark.asyncio
async def test_compile_persists_execution_isolated_per_tenant() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"ex-a-{suffix}", f"ex-b-{suffix}"
    org_a = await _create_org(slug_a)
    org_b = await _create_org(slug_b)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_a = await _register_login(client, slug_a, "admin@a.io")
            await _register_login(client, slug_b, "admin@b.io")  # tenant B exists, idle

            # ── Unauthenticated → 401, before any pipeline work ──────────────
            assert (await client.post("/v1/compile", json={"intent": "x"})).status_code == 401

            # ── A compiles an intent → 200 + a persisted execution id ────────
            resp = await client.post(
                "/v1/compile",
                headers=_bearer(token_a),
                json={"intent": "ship a feature", "context": {"locale": "fr"}},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            execution_id = uuid.UUID(body["execution_id"])
            assert body["intent"] == "ship a feature"
            assert body["is_stub"] is True  # later stages are still placeholders
            understand = next(t for t in body["trace"] if t["stage"] == "understand")
            assert understand["is_stub"] is False  # understand is real

            # ── The row is persisted under tenant A ──────────────────────────
            a_rows = await _executions_for(org_a)
            assert [e.id for e in a_rows] == [execution_id]
            persisted = a_rows[0]
            assert persisted.tenant_id == org_a
            assert persisted.prompt_version_id is None  # ad-hoc intent (0007)
            assert persisted.status == "succeeded"
            assert persisted.created_by is not None
            assert persisted.input == {
                "intent": "ship a feature",
                "context": {"locale": "fr"},
            }
            assert persisted.started_at is not None
            assert persisted.finished_at is not None

            # ── RLS: tenant B sees none of A's executions ────────────────────
            assert await _executions_for(org_b) == []
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)

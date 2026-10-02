"""Integration: artifacts CRUD + RLS isolation over HTTP.

Requires a migrated database reachable as the app role (``kompilo_app``) via
DATABASE_URL. Skips cleanly when no database is reachable, so the default
``pytest`` run (no DB) reports this as skipped, not failed.

Run against a DISPOSABLE database:

    docker compose up -d postgres            # applies 01-init.sh (pgvector + app role)
    cd backend && alembic upgrade head        # as superuser (ALEMBIC_DATABASE_URL)
    DATABASE_URL=postgresql+asyncpg://kompilo_app:...@localhost:5432/kompilo \\
        pytest tests/integration -v
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


async def _create_org(slug: str, name: str) -> uuid.UUID:
    """Seed an organization. ``organizations`` is RLS'd on ``id``, so the GUC must
    equal the new id for the INSERT's WITH CHECK to pass."""
    org_id = uuid.uuid4()
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)
        s.add(Organization(id=org_id, slug=slug, name=name))
    return org_id


async def _delete_org(org_id: uuid.UUID) -> None:
    async with session_scope() as s:
        await apply_tenant_guc(s, org_id)
        await s.execute(sa.delete(Organization).where(Organization.id == org_id))


@pytest.mark.asyncio
async def test_artifacts_crud_and_isolation() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    tid_a = str(await _create_org(f"a-{suffix}", "Org A"))
    tid_b = str(await _create_org(f"b-{suffix}", "Org B"))

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # A creates an artifact.
            created = await client.post(
                "/v1/artifacts",
                headers={"X-Tenant-ID": tid_a},
                json={"name": "strat-1", "kind": "strategy", "content": {"k": 1}},
            )
            assert created.status_code == 201, created.text
            art_id = created.json()["id"]
            assert created.json()["tenant_id"] == tid_a

            # A sees exactly its artifact; B sees none.
            list_a = await client.get("/v1/artifacts", headers={"X-Tenant-ID": tid_a})
            list_b = await client.get("/v1/artifacts", headers={"X-Tenant-ID": tid_b})
            assert [x["id"] for x in list_a.json()] == [art_id]
            assert list_b.json() == []

            # B cannot read A's artifact by id → 404 (RLS invisibility).
            get_b = await client.get(f"/v1/artifacts/{art_id}", headers={"X-Tenant-ID": tid_b})
            assert get_b.status_code == 404

            # B cannot delete A's artifact → 404; A can → 204.
            del_b = await client.delete(f"/v1/artifacts/{art_id}", headers={"X-Tenant-ID": tid_b})
            assert del_b.status_code == 404
            del_a = await client.delete(f"/v1/artifacts/{art_id}", headers={"X-Tenant-ID": tid_a})
            assert del_a.status_code == 204
    finally:
        await _delete_org(uuid.UUID(tid_a))
        await _delete_org(uuid.UUID(tid_b))

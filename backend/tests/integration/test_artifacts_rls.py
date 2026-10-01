"""Integration: artifacts CRUD + RLS isolation over HTTP.

Requires a migrated database reachable as the app role (``kompilo_app``) via
DATABASE_URL. Skips cleanly when no database is reachable, so the default
``pytest`` run (no DB) reports this as skipped, not failed.

Run against a DISPOSABLE database (it creates and deletes two tenants):

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

from app.db.session import engine, session_scope
from app.main import app
from app.models.tenant import Tenant


async def _db_reachable() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.asyncio
async def test_artifacts_crud_and_isolation() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"a-{suffix}", f"b-{suffix}"

    # Seed two tenants (control table, no RLS; app role has INSERT).
    async with session_scope() as s:
        tenant_a = Tenant(slug=slug_a, name="Tenant A")
        tenant_b = Tenant(slug=slug_b, name="Tenant B")
        s.add_all([tenant_a, tenant_b])
        await s.flush()
        tid_a, tid_b = str(tenant_a.id), str(tenant_b.id)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # A creates an artifact.
            created = await client.post(
                "/api/v1/artifacts",
                headers={"X-Tenant-ID": tid_a},
                json={"name": "strat-1", "kind": "strategy", "content": {"k": 1}},
            )
            assert created.status_code == 201, created.text
            art_id = created.json()["id"]
            assert created.json()["tenant_id"] == tid_a

            # A sees exactly its artifact; B sees none.
            list_a = await client.get("/api/v1/artifacts", headers={"X-Tenant-ID": tid_a})
            list_b = await client.get("/api/v1/artifacts", headers={"X-Tenant-ID": tid_b})
            assert [x["id"] for x in list_a.json()] == [art_id]
            assert list_b.json() == []

            # B cannot read A's artifact by id → 404 (RLS invisibility).
            get_b = await client.get(f"/api/v1/artifacts/{art_id}", headers={"X-Tenant-ID": tid_b})
            assert get_b.status_code == 404

            # B cannot delete A's artifact → 404; A can → 204.
            del_b = await client.delete(
                f"/api/v1/artifacts/{art_id}", headers={"X-Tenant-ID": tid_b}
            )
            assert del_b.status_code == 404
            del_a = await client.delete(
                f"/api/v1/artifacts/{art_id}", headers={"X-Tenant-ID": tid_a}
            )
            assert del_a.status_code == 204
    finally:
        # Cleanup: deleting tenants cascades to artifacts.
        async with session_scope() as s:
            await s.execute(sa.delete(Tenant).where(Tenant.slug.in_([slug_a, slug_b])))

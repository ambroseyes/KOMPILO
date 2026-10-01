"""TEMPLATE — RLS isolation integration test for Kompilo.

This file lives in the skill (NOT under `tests/`, so it is not collected by the
default unit-test run). Copy it into an integration suite and run it against a
database that already has the migrations applied and is reached as the
least-privilege app role (``kompilo_app``):

    mkdir -p backend/tests/integration
    cp .claude/skills/kompilo-rls/references/test_rls_isolation.py \\
       backend/tests/integration/
    # DATABASE_URL must point at a migrated DB reachable as kompilo_app
    cd backend && pytest tests/integration/test_rls_isolation.py -v

It asserts the four isolation invariants:
  1. a session scoped to tenant A sees ONLY A's rows;
  2. a session with no tenant set sees NOTHING (fail-closed);
  3. tenant A cannot write a row tagged with tenant B's id (WITH CHECK).

Use a DISPOSABLE database — the test writes and then deletes tenants.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from app.core.tenancy import apply_tenant_guc
from app.db.session import async_session_factory, engine
from app.models.tenant import PipelineRun, Tenant


async def _db_reachable() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.asyncio
async def test_rls_isolates_tenants() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    tenant_a = Tenant(slug=f"a-{suffix}", name="Tenant A")
    tenant_b = Tenant(slug=f"b-{suffix}", name="Tenant B")

    # 1. Create the two tenants (control table, no RLS).
    async with async_session_factory() as s:
        s.add_all([tenant_a, tenant_b])
        await s.commit()
        await s.refresh(tenant_a)
        await s.refresh(tenant_b)

    try:
        # 2. Insert one pipeline_run under each tenant (GUC must satisfy WITH CHECK).
        for tenant in (tenant_a, tenant_b):
            async with async_session_factory() as s:
                await apply_tenant_guc(s, tenant.id)
                s.add(PipelineRun(tenant_id=tenant.id, intent=f"run for {tenant.slug}"))
                await s.commit()

        # 3. Scoped to A → sees ONLY A's row.
        async with async_session_factory() as s:
            await apply_tenant_guc(s, tenant_a.id)
            rows = (await s.execute(select(PipelineRun))).scalars().all()
        assert len(rows) == 1, "tenant A must see exactly its own row"
        assert rows[0].tenant_id == tenant_a.id

        # 4. No tenant set → sees NOTHING (fail-closed).
        async with async_session_factory() as s:
            rows = (await s.execute(select(PipelineRun))).scalars().all()
        assert rows == [], "an unscoped session must see no tenant rows"

        # 5. A cannot write a row tagged as B (WITH CHECK rejects it).
        with pytest.raises(Exception):
            async with async_session_factory() as s:
                await apply_tenant_guc(s, tenant_a.id)
                s.add(PipelineRun(tenant_id=tenant_b.id, intent="cross-tenant write"))
                await s.commit()
    finally:
        # Cleanup: deleting tenants cascades to pipeline_runs (FK ON DELETE CASCADE).
        async with async_session_factory() as s:
            await s.execute(
                sa.delete(Tenant).where(Tenant.id.in_([tenant_a.id, tenant_b.id]))
            )
            await s.commit()

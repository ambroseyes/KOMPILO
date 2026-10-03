"""Integration: POST /v1/execute — real plan execution, cache, idempotency.

Runs against a migrated DB (RLS) + Redis, with the offline Echo STUB provider (no key),
so it is deterministic. Proves: a task compiles + executes with REAL (not estimated)
cost metadata and journaled steps; a 2nd identical call is served by the Gateway cache
with ZERO cost; and an Idempotency-Key replays the same execution. DISPOSABLE DB.
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


async def _register_login(client: httpx.AsyncClient, slug: str, email: str) -> str:
    await client.post(
        "/v1/auth/register", json={"org_slug": slug, "email": email, "password": "s3cret-pass"}
    )
    resp = await client.post(
        "/v1/auth/login", json={"org_slug": slug, "email": email, "password": "s3cret-pass"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_execute_runs_plan_caches_and_is_idempotent() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug = f"exec-{suffix}"
    org = await _create_org(slug)
    # Unique task so the Gateway fingerprint is a guaranteed cache miss on the 1st call.
    task = f"Explique la photosynthèse en trois phrases simples (ref {suffix})"

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            member = await _register_login(client, slug, "m@e.io")

            # Unauthenticated → 401.
            assert (await client.post("/v1/execute", json={"task": task})).status_code == 401

            # ── 1st execution: real (stub) run, REAL cost > 0, steps journaled. ──
            first = await client.post("/v1/execute", headers=_bearer(member), json={"task": task})
            assert first.status_code == 200, first.text
            b1 = first.json()
            assert b1["status"] == "succeeded"
            assert b1["execution_id"] and b1["output"]
            assert b1["questions"] == []
            assert b1["steps"]  # at least one journaled step
            meta1 = b1["metadata"]
            assert meta1["actual_cost"]["actual"] is True  # REAL cost, not an estimate
            assert meta1["actual_cost"]["cost_usd"] > 0
            assert meta1["cached"] is False
            assert meta1["provider_is_real"] is False  # offline Echo STUB (no key)
            assert meta1["note"]  # flags the stub

            # ── 2nd identical call: served by the cache, ZERO cost. ──────────────
            second = await client.post("/v1/execute", headers=_bearer(member), json={"task": task})
            b2 = second.json()
            assert b2["status"] == "succeeded"
            assert b2["metadata"]["cached"] is True
            assert b2["metadata"]["actual_cost"]["cost_usd"] == 0.0  # the 2nd call is free
            assert b2["output"] == b1["output"]

            # ── Idempotency-Key replays the SAME execution. ──────────────────────
            headers = {**_bearer(member), "Idempotency-Key": f"key-{suffix}"}
            e1 = await client.post("/v1/execute", headers=headers, json={"task": task})
            e2 = await client.post("/v1/execute", headers=headers, json={"task": task})
            assert e1.json()["execution_id"] == e2.json()["execution_id"]
            assert e2.json()["metadata"]["idempotent_replay"] is True

            # The executions are visible via the executions list (tenant-scoped).
            listed = await client.get("/v1/executions", headers=_bearer(member))
            assert listed.status_code == 200
            assert all(e["tenant_id"] == str(org) for e in listed.json())
    finally:
        await _delete_org(org)

"""Integration: per-tenant budgets/quotas over a real DB (RLS) + Redis.

Proves, with the offline Echo STUB (no key, deterministic): a run is metered
(attributed cost recorded, real-vs-STUB split honest); only an org admin can set
the caps; once a monthly task cap is reached the next run is refused with 402
(quality never degraded — the run simply does not start); and a tenant's budget
and usage are invisible to another tenant, whose own runs are unaffected (RLS).
Skips if no DB is reachable. DISPOSABLE DB.
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
    """Register (first user = owner, the rest = members) then log in; returns the token."""
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
async def test_budget_metering_rbac_enforcement_and_isolation() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"bud-a-{suffix}", f"bud-b-{suffix}"
    org_a = await _create_org(slug_a)
    org_b = await _create_org(slug_b)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            admin_a = await _register_login(client, slug_a, "admin@a.io")  # first user → owner
            member_a = await _register_login(client, slug_a, "member@a.io")  # second → member
            admin_b = await _register_login(client, slug_b, "admin@b.io")

            # Phrasing proven to PROCEED (not trigger the ambiguity ASK); distinct
            # refs keep each a Gateway cache miss.
            base = "Explique la photosynthèse en trois phrases simples"
            task_a = f"{base} (ref {suffix})"
            task_blocked = f"{base} (ref x{suffix})"
            task_b = f"{base} (ref b{suffix})"

            # ── Defaults: no budget row = unlimited / enforcement off, zero usage ──
            budget0 = await client.get("/v1/budget", headers=_bearer(admin_a))
            assert budget0.status_code == 200, budget0.text
            assert budget0.json() == {
                "monthly_cost_usd_limit": None,
                "monthly_task_limit": None,
                "enabled": False,
            }
            usage0 = (await client.get("/v1/usage", headers=_bearer(admin_a))).json()
            assert usage0["n_tasks"] == 0 and usage0["cost_usd"] == 0.0

            # ── A run is metered (attributed cost > 0, STUB → real spend is 0) ─────
            run = await client.post(
                "/v1/execute",
                headers=_bearer(admin_a),
                json={"task": task_a},
            )
            assert run.status_code == 200, run.text
            assert run.json()["status"] == "succeeded", run.text

            usage1 = (await client.get("/v1/usage", headers=_bearer(admin_a))).json()
            assert usage1["n_tasks"] == 1
            assert usage1["cost_usd"] > 0  # attributed cost recorded
            assert usage1["real_cost_usd"] == 0.0  # offline STUB is not real spend

            # ── RBAC: a non-admin member cannot set the caps ──────────────────────
            forbidden = await client.put(
                "/v1/budget", headers=_bearer(member_a), json={"monthly_task_limit": 1}
            )
            assert forbidden.status_code == 403, forbidden.text

            # ── Admin sets a task cap of 1 (already 1 task used this month) ────────
            put = await client.put(
                "/v1/budget",
                headers=_bearer(admin_a),
                json={"monthly_task_limit": 1, "enabled": True},
            )
            assert put.status_code == 200, put.text
            assert put.json()["monthly_task_limit"] == 1 and put.json()["enabled"] is True

            # ── Gate: the next run is refused with 402 (never degraded) ───────────
            blocked = await client.post(
                "/v1/execute",
                headers=_bearer(admin_a),
                json={"task": task_blocked},
            )
            assert blocked.status_code == 402, blocked.text
            assert "Quota mensuel de tâches" in blocked.json()["detail"]

            # ── RLS: tenant B sees its own (empty) budget/usage, A's is invisible ─
            b_budget = (await client.get("/v1/budget", headers=_bearer(admin_b))).json()
            assert b_budget["enabled"] is False and b_budget["monthly_task_limit"] is None
            b_usage = (await client.get("/v1/usage", headers=_bearer(admin_b))).json()
            assert b_usage["n_tasks"] == 0

            # ── Tenant B is NOT blocked by tenant A's cap ─────────────────────────
            b_run = await client.post(
                "/v1/execute",
                headers=_bearer(admin_b),
                json={"task": task_b},
            )
            assert b_run.status_code == 200, b_run.text
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)

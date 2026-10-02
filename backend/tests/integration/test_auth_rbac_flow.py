"""Integration: signup → login/refresh → token-scoped access → RBAC (owner/member).

Covers the item deliverables end-to-end against a real migrated DB (RLS active):
- signup creates an organization + its owner and returns access + refresh tokens;
- the access token grants API access (and /auth/me reports role="owner");
- a protected route is refused without a token and allowed with one;
- refresh exchanges a valid refresh token for new tokens (and an access token is
  rejected at /auth/refresh);
- require_role gates owner/admin-only routes (a plain member gets 403);
- a duplicate org slug on signup is a safe 409.

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

_PWD = "s3cret-pass"


async def _db_reachable() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


async def _delete_org_by_slug(slug: str) -> None:
    async with session_scope() as s:
        row = (
            await s.execute(sa.text("SELECT kompilo_resolve_org(:slug)"), {"slug": slug})
        ).scalar_one_or_none()
        if row is None:
            return
        org_id = uuid.UUID(str(row))
        await apply_tenant_guc(s, org_id)
        await s.execute(sa.delete(Organization).where(Organization.id == org_id))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_signup_login_refresh_and_rbac() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug = f"rbac-{suffix}"
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # ── Signup creates org + owner, returns tokens ─────────────────────
            signed = await client.post(
                "/v1/auth/signup",
                json={
                    "org_slug": slug,
                    "org_name": "RBAC Co",
                    "email": "owner@rbac.io",
                    "password": _PWD,
                },
            )
            assert signed.status_code == 201, signed.text
            tokens = signed.json()
            assert tokens["access_token"] and tokens["refresh_token"]
            owner = _bearer(tokens["access_token"])

            me = await client.get("/v1/auth/me", headers=owner)
            assert me.status_code == 200
            assert me.json()["role"] == "owner"
            assert me.json()["is_org_admin"] is True

            # ── Protected route: refused without a token, allowed with one ─────
            assert (await client.get("/v1/projects")).status_code == 401
            assert (await client.get("/v1/projects", headers=owner)).status_code == 200

            # ── Refresh exchanges a refresh token for new tokens ───────────────
            refreshed = await client.post(
                "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
            )
            assert refreshed.status_code == 200, refreshed.text
            new_access = refreshed.json()["access_token"]
            assert (await client.get("/v1/auth/me", headers=_bearer(new_access))).status_code == 200
            # An access token cannot be used to refresh.
            assert (
                await client.post(
                    "/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
                )
            ).status_code == 401

            # ── RBAC: owner may list members; a plain member may not (403) ─────
            assert (await client.get("/v1/organizations/members", headers=owner)).status_code == 200

            await client.post(
                "/v1/auth/register",
                json={"org_slug": slug, "email": "member@rbac.io", "password": _PWD},
            )
            member_login = await client.post(
                "/v1/auth/login",
                json={"org_slug": slug, "email": "member@rbac.io", "password": _PWD},
            )
            member = _bearer(member_login.json()["access_token"])
            member_me = await client.get("/v1/auth/me", headers=member)
            assert member_me.json()["role"] == "member"
            assert (
                await client.get("/v1/organizations/members", headers=member)
            ).status_code == 403

            # ── Duplicate org slug on signup → safe 409 ────────────────────────
            dup = await client.post(
                "/v1/auth/signup",
                json={
                    "org_slug": slug,
                    "org_name": "RBAC Co 2",
                    "email": "other@rbac.io",
                    "password": _PWD,
                },
            )
            assert dup.status_code == 409
    finally:
        await _delete_org_by_slug(slug)

"""Integration: measured version comparison over a real DB (RLS) + the improve loop.

Saves two real compilations as versions, then compares them through
``POST /prompts/{id}/versions/compare`` — asserting a numbers-backed result that is
honestly flagged (offline Echo provider → ``provider_is_real:false``). Also runs the
stateless ``POST /v1/improve/loop``. Skips if no DB is reachable. DISPOSABLE DB.

Covered:
- save v1 + v2, then a measured comparison with an explicit case set;
- the comparison is tenant-isolated (tenant B cannot compare tenant A's prompt → 404);
- a missing version is a 404; the improve loop returns a bounded trajectory.
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

TASK_A = "Rédige un message de bienvenue chaleureux pour un nouveau client"
TASK_B = "Rédige un message de bienvenue chaleureux, personnalisé et concis, pour un nouveau client"
CASE = "Souhaite la bienvenue à un nouveau client nommé Alex qui vient de s'inscrire"


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
async def test_version_comparison_and_improve_loop() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"bench-a-{suffix}", f"bench-b-{suffix}"
    org_a = await _create_org(slug_a)
    org_b = await _create_org(slug_b)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            admin = await _register_login(client, slug_a, "admin@a.io")
            other = await _register_login(client, slug_b, "admin@b.io")

            project = (
                await client.post(
                    "/v1/projects", headers=_bearer(admin), json={"slug": "alpha", "name": "Alpha"}
                )
            ).json()
            prompt = (
                await client.post(
                    "/v1/prompts",
                    headers=_bearer(admin),
                    json={"project_id": project["id"], "slug": "welcome", "name": "Welcome"},
                )
            ).json()
            prompt_id = prompt["id"]

            for task in (TASK_A, TASK_B):
                saved = await client.post(
                    f"/v1/prompts/{prompt_id}/compilations",
                    headers=_bearer(admin),
                    json={"task": task},
                )
                assert saved.status_code == 201, saved.text

            # ── Measured comparison with an explicit case set ─────────────────────
            cmp = await client.post(
                f"/v1/prompts/{prompt_id}/versions/compare",
                headers=_bearer(admin),
                json={
                    "from_version": 1,
                    "to_version": 2,
                    "cases": [{"name": "alex", "task": CASE}],
                },
            )
            assert cmp.status_code == 200, cmp.text
            body = cmp.json()
            assert body["from_version"] == 1 and body["to_version"] == 2
            assert body["verdict"] in {"to_better", "from_better", "tie"}
            assert body["from_result"]["cases"] and body["to_result"]["cases"]
            assert body["method"] == "rules-v1"
            # Offline Echo provider in tests → ranking honestly flagged as not meaningful.
            assert body["provider_is_real"] is False
            assert "STUB" in body["note"]

            # ── A missing version → 404 ───────────────────────────────────────────
            missing = await client.post(
                f"/v1/prompts/{prompt_id}/versions/compare",
                headers=_bearer(admin),
                json={"from_version": 1, "to_version": 99},
            )
            assert missing.status_code == 404

            # ── Cross-tenant isolation: tenant B cannot see A's prompt ────────────
            cross = await client.post(
                f"/v1/prompts/{prompt_id}/versions/compare",
                headers=_bearer(other),
                json={"from_version": 1, "to_version": 2},
            )
            assert cross.status_code == 404

            # ── The improve loop returns a bounded trajectory ─────────────────────
            loop = await client.post(
                "/v1/improve/loop",
                headers=_bearer(admin),
                json={"task": TASK_A, "max_iterations": 2},
            )
            assert loop.status_code == 200, loop.text
            lbody = loop.json()
            assert lbody["status"] in {"succeeded", "needs_clarification"}
            assert len(lbody["iterations"]) <= 2
            assert lbody["provider_is_real"] is False
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)

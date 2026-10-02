"""Integration: prompt library (tags/filter/pagination) + compile→save→reopen→diff.

Exercises item-"library" routes against a real migrated DB as the least-privilege app
role (RLS active). Skips if no DB is reachable. DISPOSABLE DB.

Covered:
- flat create ``POST /v1/prompts`` with tags; library list with project/tag/q filters
  and pagination (``items``/``total``/``limit``/``offset``);
- save a compilation server-side (``POST /prompts/{id}/compilations``) → version 1,
  snapshotting catr/ir/renders/diagnostics; reopen the history; save version 2;
- neutral diff between v1 and v2;
- cross-tenant isolation (tenant B sees none of A's prompts and cannot diff them).
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

# Clear "write X" tasks that the Ambiguity Engine lets PROCEED (no CRITICAL gap),
# so the compile yields renders/ir to snapshot.
TASK_A = "Rédige un message de bienvenue chaleureux pour un nouveau client"
TASK_B = "Rédige un email de relance poli pour une facture impayée"


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
async def test_library_filters_pagination_save_and_diff() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"lib-a-{suffix}", f"lib-b-{suffix}"
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
            project_id = project["id"]

            # ── Flat create with tags (tags normalized: lowercased, de-duped) ──────
            created = await client.post(
                "/v1/prompts",
                headers=_bearer(admin),
                json={
                    "project_id": project_id,
                    "slug": "welcome",
                    "name": "Welcome message",
                    "tags": ["Demo", "welcome", "demo"],  # dup + mixed case
                },
            )
            assert created.status_code == 201, created.text
            prompt = created.json()
            prompt_id = prompt["id"]
            assert prompt["tags"] == ["demo", "welcome"]

            # A second prompt (different tags) to make filtering meaningful.
            await client.post(
                "/v1/prompts",
                headers=_bearer(admin),
                json={
                    "project_id": project_id,
                    "slug": "invoice",
                    "name": "Invoice reminder",
                    "tags": ["billing"],
                },
            )

            # ── Library list: filters + pagination ────────────────────────────────
            page = (await client.get("/v1/prompts", headers=_bearer(admin))).json()
            assert page["total"] == 2 and page["limit"] == 20 and page["offset"] == 0
            assert {p["slug"] for p in page["items"]} == {"welcome", "invoice"}

            # Filter by tag (containment) → only the welcome prompt.
            by_tag = (
                await client.get("/v1/prompts", headers=_bearer(admin), params={"tag": "demo"})
            ).json()
            assert [p["slug"] for p in by_tag["items"]] == ["welcome"]
            # Unknown tag → empty.
            none = (
                await client.get("/v1/prompts", headers=_bearer(admin), params={"tag": "nope"})
            ).json()
            assert none["total"] == 0 and none["items"] == []
            # Text search over name/slug/description.
            by_q = (
                await client.get("/v1/prompts", headers=_bearer(admin), params={"q": "invoice"})
            ).json()
            assert [p["slug"] for p in by_q["items"]] == ["invoice"]
            # Project filter + pagination (limit=1 returns one row but the full total).
            paged = (
                await client.get(
                    "/v1/prompts",
                    headers=_bearer(admin),
                    params={"project_id": project_id, "limit": 1, "offset": 0},
                )
            ).json()
            assert paged["total"] == 2 and len(paged["items"]) == 1 and paged["limit"] == 1

            # ── Save a compilation → version 1 (snapshot of a real compile) ───────
            save1 = await client.post(
                f"/v1/prompts/{prompt_id}/compilations",
                headers=_bearer(admin),
                json={"task": TASK_A},
            )
            assert save1.status_code == 201, save1.text
            body1 = save1.json()
            assert body1["version"]["version"] == 1
            assert body1["version"]["catr"] is not None  # CATR snapshotted
            assert body1["version"]["renders"] is not None  # PROCEED → renders present
            assert body1["compile"]["understood"]["objective"]  # compile echoed back

            # ── Reopen the history, then save version 2 ───────────────────────────
            hist = (
                await client.get(f"/v1/prompts/{prompt_id}/versions", headers=_bearer(admin))
            ).json()
            assert [v["version"] for v in hist] == [1]

            save2 = await client.post(
                f"/v1/prompts/{prompt_id}/compilations",
                headers=_bearer(admin),
                json={"task": TASK_B},
            )
            assert save2.status_code == 201, save2.text
            assert save2.json()["version"]["version"] == 2

            # ── Diff v1 ↔ v2 (neutral) ────────────────────────────────────────────
            diff = await client.get(
                f"/v1/prompts/{prompt_id}/versions/diff",
                headers=_bearer(admin),
                params={"from_version": 1, "to_version": 2},
            )
            assert diff.status_code == 200, diff.text
            d = diff.json()
            assert d["from_version"] == 1 and d["to_version"] == 2
            assert len(d["renders"]) == 3  # compact / professional / expert
            assert any(c["path"] == "objective" for c in d["catr_fields"])  # objective changed
            assert "sans mesure" in d["note"].lower()  # neutral: explicitly no verdict

            # Out-of-range version → 404.
            missing = await client.get(
                f"/v1/prompts/{prompt_id}/versions/diff",
                headers=_bearer(admin),
                params={"from_version": 1, "to_version": 99},
            )
            assert missing.status_code == 404

            # ── Cross-tenant isolation ────────────────────────────────────────────
            b_page = (await client.get("/v1/prompts", headers=_bearer(other))).json()
            assert b_page["total"] == 0 and b_page["items"] == []
            assert (
                await client.get(f"/v1/prompts/{prompt_id}", headers=_bearer(other))
            ).status_code == 404
            assert (
                await client.get(
                    f"/v1/prompts/{prompt_id}/versions/diff",
                    headers=_bearer(other),
                    params={"from_version": 1, "to_version": 2},
                )
            ).status_code == 404
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)

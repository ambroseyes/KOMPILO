"""Integration: RAG corpus ingestion + retrieval over a real DB, tenant-isolated (RLS).

Ingests documents, searches the corpus (pgvector similarity), and asserts: chunks are
produced and embedded; search ranks the lexically-closest chunk first; results are
honestly flagged over offline embeddings (``is_real=false`` + note); and a tenant can
never see or search another tenant's corpus (RLS). Skips if no DB is reachable.
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

# Long enough (each paragraph > 400 chars) to split into several chunks on ingestion.
_FILLER = " ".join(["Détail de la procédure d'accueil interne."] * 12)
DOC_WELCOME = (
    "Toujours saluer le nouveau client par son prénom et le remercier de son inscription. "
    + _FILLER
    + "\n\n"
    + "Proposer ensuite une prise en main guidée du produit, étape par étape. "
    + _FILLER
    + "\n\n"
    + "Clôturer en rappelant le canal de support disponible. "
    + _FILLER
)
DOC_BILLING = "Les remboursements sont traités sous quatorze jours ouvrés. " + " ".join(
    ["Règle de facturation applicable à tout abonnement."] * 12
)


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
async def test_ingestion_retrieval_and_tenant_isolation() -> None:
    if not await _db_reachable():
        pytest.skip("No database reachable at DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    slug_a, slug_b = f"rag-a-{suffix}", f"rag-b-{suffix}"
    org_a = await _create_org(slug_a)
    org_b = await _create_org(slug_b)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            tok_a = await _register_login(client, slug_a, "admin@a.io")
            tok_b = await _register_login(client, slug_b, "admin@b.io")

            # ── Tenant A ingests two documents ────────────────────────────────────
            ingest = await client.post(
                "/v1/documents",
                headers=_bearer(tok_a),
                json={"title": "Accueil", "content": DOC_WELCOME},
            )
            assert ingest.status_code == 201, ingest.text
            body = ingest.json()
            assert body["n_chunks"] >= 2
            # Offline embeddings in tests → honestly flagged, never presented as real.
            assert body["embedding_is_real"] is False
            assert body["note"]
            doc_a_id = body["document"]["id"]

            await client.post(
                "/v1/documents",
                headers=_bearer(tok_a),
                json={"title": "Facturation", "content": DOC_BILLING},
            )

            # ── Search ranks the lexically-closest chunk first ───────────────────
            search = await client.post(
                "/v1/documents/search",
                headers=_bearer(tok_a),
                json={"query": "saluer le nouveau client par son prénom", "k": 3},
            )
            assert search.status_code == 200, search.text
            sbody = search.json()
            assert sbody["is_real"] is False and sbody["note"]
            assert sbody["chunks"], "expected at least one retrieved chunk"
            assert "prénom" in sbody["chunks"][0]["content"]

            # ── Listing is scoped to the tenant ──────────────────────────────────
            listing = await client.get("/v1/documents", headers=_bearer(tok_a))
            assert listing.status_code == 200
            assert {d["title"] for d in listing.json()} == {"Accueil", "Facturation"}

            # ── RLS: tenant B sees an empty corpus and cannot read A's document ───
            b_list = await client.get("/v1/documents", headers=_bearer(tok_b))
            assert b_list.status_code == 200 and b_list.json() == []

            b_get = await client.get(f"/v1/documents/{doc_a_id}", headers=_bearer(tok_b))
            assert b_get.status_code == 404

            b_search = await client.post(
                "/v1/documents/search",
                headers=_bearer(tok_b),
                json={"query": "saluer le nouveau client par son prénom"},
            )
            assert b_search.status_code == 200
            assert b_search.json()["chunks"] == []  # none of A's chunks leak to B
    finally:
        await _delete_org(org_a)
        await _delete_org(org_b)

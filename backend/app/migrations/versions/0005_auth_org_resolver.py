"""Auth: SECURITY DEFINER function to resolve an org slug -> id for login

``organizations`` is RLS-restricted to the current tenant (``id = app.tenant_id``),
so a login attempt cannot look an org up by slug before any tenant context exists
(chicken-and-egg). This narrow SECURITY DEFINER function returns ONLY the id for an
exact slug, running as the (superuser) owner so it bypasses RLS for that one lookup
— it exposes nothing beyond the id of a slug the caller already knows.

Revision ID: 0005_auth_org_resolver
Revises: 0004_mvp_rls
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_auth_org_resolver"
down_revision: str | None = "0004_mvp_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION kompilo_resolve_org(p_slug text)
        RETURNS uuid
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT id FROM organizations WHERE slug = p_slug;
        $$;
        """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS kompilo_resolve_org(text)")

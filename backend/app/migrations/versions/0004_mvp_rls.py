"""Enable RLS (ENABLE + FORCE) + tenant_isolation policy on every tenant table

Separate migration (DDL for Row-Level Security only). Each tenant-owned table gets
a ``tenant_isolation`` policy filtering by ``tenant_id``; the tenant root
``organizations`` filters by ``id``. ``current_setting('app.tenant_id', true)``
uses the missing_ok flag so an unset tenant yields NULL → zero rows (fail-closed)
rather than erroring. FORCE applies RLS even to the table owner (defense-in-depth;
superusers still bypass, which is migrations/admin only).

Revision ID: 0004_mvp_rls
Revises: 0003_mvp_schema
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_mvp_rls"
down_revision: str | None = "0003_mvp_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tenant-owned tables: policy on tenant_id.
TENANT_OWNED: tuple[str, ...] = (
    "users",
    "teams",
    "memberships",
    "projects",
    "prompts",
    "prompt_versions",
    "executions",
    "artifacts",
)

# NULLIF(..., '') is essential: on a pooled connection a prior SET LOCAL leaves the
# custom GUC as '' (empty string) after reset, and ''::uuid raises. Mapping '' → NULL
# makes an unset tenant match zero rows (fail-closed) instead of erroring.
_GUC = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _enable_force(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _policy(table: str, column: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({column} = {_GUC}) WITH CHECK ({column} = {_GUC})"
    )


def upgrade() -> None:
    # Tenant root: isolate by id (an org sees only itself).
    _enable_force("organizations")
    _policy("organizations", "id")

    # Tenant-owned tables: isolate by tenant_id.
    for table in TENANT_OWNED:
        _enable_force(table)
        _policy(table, "tenant_id")


def downgrade() -> None:
    for table in (*TENANT_OWNED, "organizations"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")

    # Restore artifacts to its pre-0004 state (ENABLE + app.current_tenant policy
    # from migration 0002); leave it RLS-enabled.
    op.execute(
        "CREATE POLICY tenant_isolation ON artifacts "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )

    # Disable RLS on the newly-created MVP tables (they had none before 0004).
    for table in (
        "users",
        "teams",
        "memberships",
        "projects",
        "prompts",
        "prompt_versions",
        "executions",
        "organizations",
    ):
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

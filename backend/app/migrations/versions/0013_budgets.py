"""Per-tenant budgets + usage ledger — tenant-scoped with RLS

Adds ``tenant_budgets`` (at most one optional cap row per tenant) and
``usage_records`` (append-only metering ledger, one row per succeeded run). Both
get the standard ``tenant_isolation`` RLS policy (ENABLE + FORCE). The budget
gate sums ``usage_records`` for the current month and refuses a new run once a
cap is reached — it never degrades the run.

Revision ID: 0013_budgets
Revises: 0012_documents
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_budgets"
down_revision: str | None = "0012_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})"
    )


def upgrade() -> None:
    # ── tenant_budgets: one optional cap row per tenant ──────────────────────────
    op.create_table(
        "tenant_budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("monthly_cost_usd_limit", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("monthly_task_limit", sa.BigInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_budgets"),
        # One budget per tenant; the unique index also serves the tenant_id lookup.
        sa.UniqueConstraint("tenant_id", name="uq_tenant_budgets_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_tenant_budgets_tenant_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_tenant_budgets_created_by_users",
            ondelete="SET NULL",
        ),
    )

    # ── usage_records: append-only metering ledger ───────────────────────────────
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=12, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("input_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "provider_is_real", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usage_records"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_usage_records_tenant_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name="fk_usage_records_execution_id_executions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_usage_records_created_by_users",
            ondelete="SET NULL",
        ),
    )
    # The period-sum query filters by (tenant_id, created_at); this composite covers it
    # and, leading with tenant_id, also serves plain tenant_id lookups.
    op.create_index(
        "ix_usage_records_tenant_id_created_at", "usage_records", ["tenant_id", "created_at"]
    )

    _enable_rls("tenant_budgets")
    _enable_rls("usage_records")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON usage_records")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenant_budgets")
    op.drop_index("ix_usage_records_tenant_id_created_at", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_table("tenant_budgets")

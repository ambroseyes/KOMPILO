"""Execution steps journal + nullable executions.prompt_version_id

Adds ``execution_steps`` (one journaled step per plan step: input, output, tokens, REAL
cost, model, cached, latency) with RLS, and relaxes ``executions.prompt_version_id`` to
nullable so an execution can run a standalone plan (from a raw task) with no version.

Revision ID: 0009_execution_steps
Revises: 0008_user_role
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_execution_steps"
down_revision: str | None = "0008_user_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.alter_column(
        "executions", "prompt_version_id", existing_type=postgresql.UUID(), nullable=True
    )

    op.create_table(
        "execution_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_usd", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("cached", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_execution_steps"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name="fk_execution_steps_tenant_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_steps_execution_id_executions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_execution_steps_tenant_id", "execution_steps", ["tenant_id"])
    op.create_index(
        "ix_execution_steps_tenant_id_execution_id",
        "execution_steps",
        ["tenant_id", "execution_id"],
    )

    op.execute("ALTER TABLE execution_steps ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE execution_steps FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON execution_steps "
        f"USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON execution_steps")
    op.drop_index("ix_execution_steps_tenant_id_execution_id", table_name="execution_steps")
    op.drop_index("ix_execution_steps_tenant_id", table_name="execution_steps")
    op.drop_table("execution_steps")
    op.alter_column(
        "executions", "prompt_version_id", existing_type=postgresql.UUID(), nullable=False
    )

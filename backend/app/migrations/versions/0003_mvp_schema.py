"""MVP schema: organizations + IAM + content; retire bootstrap tables

Creates the canonical MVP schema (organizations as the tenant root, users, teams,
memberships, projects, prompts, prompt_versions, executions), re-points the kept
``artifacts`` table onto ``organizations``, and drops the demo bootstrap tables
(``pipeline_runs``, ``tenants``). RLS is handled separately in 0004.

Revision ID: 0003_mvp_schema
Revises: 0002_artifacts
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_mvp_schema"
down_revision: str | None = "0002_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts_columns() -> list[sa.Column[Any]]:
    return [
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
    ]


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"],
        ["organizations.id"],
        name=f"fk_{table}_tenant_id_organizations",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    # ── organizations (tenant root) ──────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    # ── users (tenant-scoped identity) ───────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_org_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        _tenant_fk("users"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # ── teams ────────────────────────────────────────────────────────────────
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_teams"),
        _tenant_fk("teams"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_teams_tenant_id_slug"),
    )
    op.create_index("ix_teams_tenant_id", "teams", ["tenant_id"])

    # ── memberships (user ↔ team) ────────────────────────────────────────────
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), server_default=sa.text("'member'"), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        _tenant_fk("memberships"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="fk_memberships_team_id_teams", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "team_id", name="uq_memberships_tenant_id_user_id_team_id"
        ),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])
    op.create_index("ix_memberships_tenant_id_user_id", "memberships", ["tenant_id", "user_id"])
    op.create_index("ix_memberships_tenant_id_team_id", "memberships", ["tenant_id", "team_id"])

    # ── projects (content) ───────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        *_ts_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        _tenant_fk("projects"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="fk_projects_team_id_teams", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_projects_created_by_users", ondelete="SET NULL"
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_projects_tenant_id_slug"),
    )
    op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"])
    op.create_index("ix_projects_tenant_id_team_id", "projects", ["tenant_id", "team_id"])

    # ── prompts (content) ────────────────────────────────────────────────────
    op.create_table(
        "prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        *_ts_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_prompts"),
        _tenant_fk("prompts"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_prompts_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_prompts_created_by_users", ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "slug", name="uq_prompts_tenant_id_project_id_slug"
        ),
    )
    op.create_index("ix_prompts_tenant_id", "prompts", ["tenant_id"])
    op.create_index("ix_prompts_tenant_id_project_id", "prompts", ["tenant_id", "project_id"])

    # ── prompt_versions (content) ────────────────────────────────────────────
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("catr", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ir", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("renders", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_target", sa.String(length=100), nullable=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_ts_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_prompt_versions"),
        _tenant_fk("prompt_versions"),
        sa.ForeignKeyConstraint(
            ["prompt_id"],
            ["prompts.id"],
            name="fk_prompt_versions_prompt_id_prompts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name="fk_prompt_versions_author_id_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "prompt_id",
            "version",
            name="uq_prompt_versions_tenant_id_prompt_id_version",
        ),
    )
    op.create_index("ix_prompt_versions_tenant_id", "prompt_versions", ["tenant_id"])
    op.create_index(
        "ix_prompt_versions_tenant_id_prompt_id", "prompt_versions", ["tenant_id", "prompt_id"]
    )

    # ── executions (content) ─────────────────────────────────────────────────
    op.create_table(
        "executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        *_ts_columns(),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_executions"),
        _tenant_fk("executions"),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
            name="fk_executions_prompt_version_id_prompt_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_executions_created_by_users", ondelete="SET NULL"
        ),
    )
    op.create_index("ix_executions_tenant_id", "executions", ["tenant_id"])
    op.create_index(
        "ix_executions_tenant_id_prompt_version_id",
        "executions",
        ["tenant_id", "prompt_version_id"],
    )
    op.create_index("ix_executions_tenant_id_status", "executions", ["tenant_id", "status"])

    # ── Re-point the kept artifacts table from tenants → organizations ───────
    op.drop_constraint("fk_artifacts_tenant_id_tenants", "artifacts", type_="foreignkey")
    op.create_foreign_key(
        "fk_artifacts_tenant_id_organizations",
        "artifacts",
        "organizations",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── Drop the demo bootstrap tables (policies drop with the tables) ───────
    op.drop_table("pipeline_runs")
    op.drop_table("tenants")


def downgrade() -> None:
    # Recreate the bootstrap tables so the chain back to 0002/0001 stays valid.
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_runs"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_pipeline_runs_tenant_id_tenants",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_pipeline_runs_tenant_id", "pipeline_runs", ["tenant_id"])

    # Re-point artifacts back to tenants.
    op.drop_constraint("fk_artifacts_tenant_id_organizations", "artifacts", type_="foreignkey")
    op.create_foreign_key(
        "fk_artifacts_tenant_id_tenants",
        "artifacts",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    for table in (
        "executions",
        "prompt_versions",
        "prompts",
        "projects",
        "memberships",
        "teams",
        "users",
        "organizations",
    ):
        op.drop_table(table)

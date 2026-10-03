"""Partial unique slug indexes for soft-deletable content (projects, prompts)

Replaces the full ``UNIQUE (tenant_id, slug)`` / ``UNIQUE (tenant_id, project_id,
slug)`` constraints with PARTIAL unique indexes scoped to live rows
(``WHERE deleted_at IS NULL``). This lets a slug be reused after its owner is
soft-deleted, while still forbidding two LIVE rows from sharing a slug within a
tenant (projects) or a project (prompts).

``prompt_versions`` deliberately keeps its FULL ``UNIQUE (tenant_id, prompt_id,
version)`` constraint: version numbers are monotonic and never reused, even after a
version is soft-deleted, so the allocator counts soft-deleted rows too.

Revision ID: 0006_partial_unique_slugs
Revises: 0006_prompt_version_content
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_partial_unique_slugs"
# Chained after 0006_prompt_version_content (both once branched off 0005, creating
# two Alembic heads; linearized here so `alembic upgrade head` is unambiguous).
down_revision: str | None = "0006_prompt_version_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = sa.text("deleted_at IS NULL")


def upgrade() -> None:
    # projects: full UNIQUE constraint → partial unique index (live rows only).
    op.drop_constraint("uq_projects_tenant_id_slug", "projects", type_="unique")
    op.create_index(
        "uq_projects_tenant_id_slug",
        "projects",
        ["tenant_id", "slug"],
        unique=True,
        postgresql_where=_LIVE,
    )

    # prompts: full UNIQUE constraint → partial unique index (live rows only).
    op.drop_constraint("uq_prompts_tenant_id_project_id_slug", "prompts", type_="unique")
    op.create_index(
        "uq_prompts_tenant_id_project_id_slug",
        "prompts",
        ["tenant_id", "project_id", "slug"],
        unique=True,
        postgresql_where=_LIVE,
    )


def downgrade() -> None:
    op.drop_index("uq_prompts_tenant_id_project_id_slug", table_name="prompts")
    op.create_unique_constraint(
        "uq_prompts_tenant_id_project_id_slug",
        "prompts",
        ["tenant_id", "project_id", "slug"],
    )

    op.drop_index("uq_projects_tenant_id_slug", table_name="projects")
    op.create_unique_constraint(
        "uq_projects_tenant_id_slug",
        "projects",
        ["tenant_id", "slug"],
    )

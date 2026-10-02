"""Add immutable ``content`` (prompt source) to prompt_versions

A prompt version captures the IMMUTABLE source text of a prompt at a point in
time. The pipeline-output JSONB columns (``catr``/``ir``/...) are derived and
filled later, but the versioned source itself lives in ``content`` and never
changes — a new revision is a new ``prompt_versions`` row. This migration adds
that column. ``prompt_versions`` is a fresh MVP table (introduced in 0003) with
no production rows, so the column is added NOT NULL directly.

RLS is untouched: the ``tenant_isolation`` policy created in 0004 already covers
the whole row, including the new column.

Revision ID: 0006_prompt_version_content
Revises: 0005_auth_org_resolver
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_prompt_version_content"
down_revision: str | None = "0005_auth_org_resolver"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prompt_versions",
        sa.Column("content", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("prompt_versions", "content")

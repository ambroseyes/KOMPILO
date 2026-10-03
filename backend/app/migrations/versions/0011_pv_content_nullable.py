"""Make prompt_versions.content nullable (library versioning compatibility)

``content`` (added NOT NULL in 0006_prompt_version_content) held the immutable source
text of a version in the earlier design. The library's Version Manager snapshots a
compilation into ``catr``/``ir``/``renders``/``diagnostics`` instead and does not always
have a single ``content`` string, so the column is relaxed to nullable — kept for
compatibility, populated when a render is available. RLS is untouched.

Revision ID: 0011_pv_content_nullable
Revises: 0010_prompt_tags
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_pv_content_nullable"
down_revision: str | None = "0010_prompt_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("prompt_versions", "content", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    # Backfill NULLs so the NOT NULL constraint can be restored.
    op.execute("UPDATE prompt_versions SET content = '' WHERE content IS NULL")
    op.alter_column("prompt_versions", "content", existing_type=sa.Text(), nullable=False)

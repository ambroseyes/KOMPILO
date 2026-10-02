"""Add prompt_versions.source_intent (raw intent the `understand` stage analyzes)

A prompt version compiles from a raw human intent. The `understand` stage reads
``source_intent`` and writes the structured result into ``catr``. Nullable so
existing rows and versions created before this field remain valid. Column-level
privileges follow the table grant (see 01-init.sh); RLS is unaffected.

Revision ID: 0007_pv_source_intent
Revises: 0006_partial_unique_slugs
Create Date: 2026-10-02

Note: the revision id is kept <= 32 chars to fit alembic_version.version_num.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_pv_source_intent"
down_revision: str | None = "0006_partial_unique_slugs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prompt_versions",
        sa.Column("source_intent", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prompt_versions", "source_intent")

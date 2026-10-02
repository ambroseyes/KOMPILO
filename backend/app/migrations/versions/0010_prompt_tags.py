"""Add prompts.tags (text[]) for the prompt library's tag filtering

Tags live on the PROMPT (the unit the library organizes and filters), not on a
version. Stored as a Postgres ``text[]`` with a GIN index so ``tags @> ARRAY[...]``
containment filters stay index-backed. ``prompts`` already has RLS (migration 0004),
so no policy change is needed.

Revision ID: 0010_prompt_tags
Revises: 0009_execution_steps
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_prompt_tags"
down_revision: str | None = "0009_execution_steps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String(length=63)),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
    )
    op.create_index("ix_prompts_tags", "prompts", ["tags"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_prompts_tags", table_name="prompts")
    op.drop_column("prompts", "tags")

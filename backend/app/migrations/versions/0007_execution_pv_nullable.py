"""Make ``executions.prompt_version_id`` nullable

Until now an execution always referenced a stored ``prompt_versions`` row. The
real ``understand`` stage lets ``/compile`` run on an ad-hoc *intent* that is not
tied to any stored version, yet we still want to persist an ``Execution`` for
every run (audit trail, future async pipeline). So ``prompt_version_id`` becomes
OPTIONAL: NULL means "ad-hoc intent compile, not bound to a stored version".

RLS is untouched: the ``tenant_isolation`` policy created in 0004 already covers
the whole row. The ``tenant_id`` column stays NOT NULL — only the prompt-version
link relaxes.

Revision ID: 0007_execution_pv_nullable
Revises: 0006_prompt_version_content
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_execution_pv_nullable"
down_revision: str | None = "0006_prompt_version_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "executions",
        "prompt_version_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # Reversible only when no NULL rows exist; ad-hoc runs would block it, which
    # is the intended guard against silently dropping them.
    op.alter_column(
        "executions",
        "prompt_version_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

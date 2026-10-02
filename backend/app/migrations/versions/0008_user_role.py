"""Replace users.is_org_admin (bool) with users.role (owner/admin/member)

Introduces an org-level RBAC role as the single source of truth and retires the
``is_org_admin`` boolean (now a derived property on the model). Existing admins are
backfilled to ``admin`` (owner can't be inferred retroactively; signup assigns it
going forward). A CHECK constrains the allowed values.

Revision ID: 0008_user_role
Revises: 0007_pv_source_intent
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_user_role"
down_revision: str | None = "0007_pv_source_intent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=16), nullable=False, server_default="member"),
    )
    # Name "role" + the metadata naming convention -> final "ck_users_role".
    op.create_check_constraint("role", "users", "role IN ('owner', 'admin', 'member')")
    # Backfill from the retiring boolean: admins -> 'admin', others -> 'member'.
    op.execute("UPDATE users SET role = 'admin' WHERE is_org_admin = true")
    op.drop_column("users", "is_org_admin")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_org_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute("UPDATE users SET is_org_admin = true WHERE role IN ('owner', 'admin')")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")

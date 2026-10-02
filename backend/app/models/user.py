"""User — a tenant-scoped identity (one user belongs to one organization)."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.roles import ADMIN_ROLES, DEFAULT_ROLE
from app.db.base import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Composite unique starting with tenant_id (also the lookup index).
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
        # Final name becomes ``ck_users_role`` via the metadata naming convention.
        CheckConstraint("role IN ('owner', 'admin', 'member')", name="role"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Org-level RBAC role (owner/admin/member); the single source of truth.
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DEFAULT_ROLE, server_default=text(f"'{DEFAULT_ROLE}'")
    )

    @property
    def is_org_admin(self) -> bool:
        """Derived: an owner or admin. Kept for callers that gate on "org admin"."""
        return self.role in ADMIN_ROLES

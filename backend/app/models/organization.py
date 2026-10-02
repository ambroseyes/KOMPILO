"""Organization — the tenant root. ``organizations.id`` IS the tenant id.

Not tenant-owned (it has no ``tenant_id`` column); its RLS policy restricts a
session to its own row via ``id = current_setting('app.tenant_id')`` (see the
RLS migration).
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

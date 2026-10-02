"""Artifact — a tenant-scoped output produced around the Kompilo pipeline.

TENANT-SCOPED — RLS enforced; ``tenant_id`` references the tenant root
(``organizations``). Access only via ``app.api.deps.TenantSession`` (see the
``kompilo-rls`` skill).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Artifact(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'other'"))
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

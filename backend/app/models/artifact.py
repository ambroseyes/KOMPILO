"""Artifact — a tenant-scoped output produced around the Kompilo pipeline."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Artifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A stored artifact (strategy, plan, report…). TENANT-SCOPED — RLS enforced.

    The RLS policy on this table is created in migration 0002. Access it only via
    the tenant-scoped session (``app.api.deps.TenantSession``); see the
    ``kompilo-rls`` skill.
    """

    __tablename__ = "artifacts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="other")
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

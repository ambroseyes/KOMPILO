"""Tenant registry and an example tenant-scoped entity (pipeline runs)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant (organization). Control table — not itself RLS-restricted."""

    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class PipelineRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single run of the Kompilo pipeline — TENANT-SCOPED (RLS enforced).

    The RLS policy on this table is created in the initial Alembic migration.
    """

    __tablename__ = "pipeline_runs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

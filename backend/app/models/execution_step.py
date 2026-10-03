"""ExecutionStep — one journaled step of a plan execution (tenant-scoped)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ExecutionStep(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "execution_steps"
    __table_args__ = (
        Index("ix_execution_steps_tenant_id_execution_id", "tenant_id", "execution_id"),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    input: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # REAL cost in USD (0 on a cache hit / unpriced model).
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

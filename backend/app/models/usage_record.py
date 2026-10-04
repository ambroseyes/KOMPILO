"""UsageRecord — append-only metering ledger (one row per metered execution).

Written once, on the SINGLE persistence path (``execution_store.persist_success``),
for every succeeded run — sync ``/v1/execute`` and the async worker alike. Never
updated or deleted: it is accounting, so it has no soft-delete. Current-period
consumption is a SUM over this table for the current UTC month; the budget gate
reads that sum before letting a new run start.

Honesty: ``provider_is_real`` records whether the run used a real model. Every
run carries an attributed ``cost_usd`` (real token count × registry price),
STUB included; the snapshot sums real-provider cost separately so offline STUB
spend is never dressed up as real.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Numeric, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class UsageRecord(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """TENANT-SCOPED, append-only. RLS policy created in the migration."""

    __tablename__ = "usage_records"
    __table_args__ = (
        # The period-sum query filters by tenant_id + created_at.
        Index("ix_usage_records_tenant_id_created_at", "tenant_id", "created_at"),
    )

    # SET NULL (not CASCADE): the accounting row outlives the execution it came from.
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("executions.id", ondelete="SET NULL"), nullable=True
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, server_default=text("0")
    )
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    provider_is_real: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

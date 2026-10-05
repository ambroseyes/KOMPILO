"""TenantBudget — a tenant's optional monthly cost / volume caps (RLS-scoped).

At most ONE row per tenant (unique ``tenant_id``). A tenant with no row is
*unlimited* — enforcement is strictly opt-in, so existing tenants are never
blocked by default. ``enabled`` lets an admin pause enforcement without losing
the configured limits. A ``None`` limit means "no cap on that axis".

The limits are a VOLUME/COST gate, never a quality lever: when a cap is reached
the next run is refused with a clear message — the output is never degraded.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, ForeignKey, Numeric, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TenantBudget(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """TENANT-SCOPED — one budget config per tenant. RLS policy in the migration."""

    __tablename__ = "tenant_budgets"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_budgets_tenant_id"),)

    # None = no cap on that axis. Numeric (not float) so monthly sums stay exact.
    monthly_cost_usd_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    monthly_task_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

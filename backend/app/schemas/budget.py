"""Budget + usage API schemas.

``BudgetRead`` / ``BudgetUpdate`` are the per-tenant caps (admin-managed).
``UsageSnapshot`` is the current-period consumption vs those caps, with the
real-vs-STUB split kept explicit so offline runs are never shown as real spend.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    monthly_cost_usd_limit: float | None
    monthly_task_limit: int | None
    enabled: bool


class BudgetUpdate(BaseModel):
    """Set the tenant's caps. ``None`` on an axis means "no cap" there."""

    monthly_cost_usd_limit: float | None = Field(default=None, ge=0)
    monthly_task_limit: int | None = Field(default=None, ge=0)
    enabled: bool = True


class UsageSnapshot(BaseModel):
    """Consumption for the current UTC month, plus the caps and what remains."""

    period_start: datetime
    cost_usd: float
    real_cost_usd: float  # spend from REAL providers only (offline STUB runs excluded)
    input_tokens: int
    output_tokens: int
    n_tasks: int

    monthly_cost_usd_limit: float | None
    monthly_task_limit: int | None
    enabled: bool
    cost_remaining_usd: float | None  # None when no cost cap is set
    tasks_remaining: int | None  # None when no task cap is set

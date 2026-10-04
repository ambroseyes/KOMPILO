"""Per-tenant cost/volume budgets: metering, the pre-run gate, and admin config.

Design notes:
- **Opt-in.** No budget row → unlimited. A disabled row → unlimited. Only an
  enabled row with a set cap can block, so existing tenants are never surprised.
- **Never degrades quality.** The gate refuses the *next* run once a cap is
  reached (HTTP 402); it never trims context or downgrades the model.
- **Metered on the single persistence path.** ``record_usage`` is called from
  ``execution_store.persist_success`` for every succeeded run (sync route and
  async worker alike), so there is exactly one accounting write per run.
- **Honest.** The cost cap enforces on the attributed cost of every run (real
  token count × registry price), so it works even with the offline STUB; the
  real-vs-STUB split (``provider_is_real``) is surfaced separately in the usage
  snapshot rather than hidden, so STUB cost is never passed off as real spend.
- **Period** = the current calendar month in the database timezone (normally
  UTC), via ``date_trunc('month', now())``; the gate and the snapshot use the
  very same expression, so they always agree.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import TenantBudget
from app.models.usage_record import UsageRecord
from app.schemas.budget import BudgetUpdate, UsageSnapshot


def budget_breach(
    *,
    enabled: bool,
    cost_limit: float | None,
    task_limit: int | None,
    cost_used: float,
    tasks_used: int,
) -> str | None:
    """Pure gate decision. Returns a user-facing French reason, or ``None`` to allow.

    A cap is breached when consumption has reached it (``>=``): the run that
    crosses the line completes, the next one is refused. Kept side-effect-free so
    the boundary logic is unit-tested without a database.
    """
    if not enabled:
        return None
    if cost_limit is not None and cost_used >= cost_limit:
        return (
            f"Budget mensuel de coût atteint ({cost_used:.4f} / {cost_limit:.4f} USD "
            "ce mois-ci). Un administrateur de l'organisation peut relever le plafond "
            "dans les réglages de budget."
        )
    if task_limit is not None and tasks_used >= task_limit:
        return (
            f"Quota mensuel de tâches atteint ({tasks_used} / {task_limit} ce mois-ci). "
            "Un administrateur de l'organisation peut relever le plafond."
        )
    return None


async def get_budget(db: AsyncSession, tenant_id: uuid.UUID) -> TenantBudget | None:
    """The tenant's budget row (RLS already scopes it); ``None`` if unset."""
    stmt = select(TenantBudget).where(TenantBudget.tenant_id == tenant_id)
    return (await db.execute(stmt)).scalars().first()


async def upsert_budget(
    db: AsyncSession, tenant_id: uuid.UUID, *, created_by: uuid.UUID | None, data: BudgetUpdate
) -> TenantBudget:
    """Create or update the tenant's single budget row. ``tenant_id`` is server-set."""
    budget = await get_budget(db, tenant_id)
    if budget is None:
        budget = TenantBudget(tenant_id=tenant_id, created_by=created_by)
        db.add(budget)
    # Decimal(str(...)) keeps the stored value free of float binary noise.
    budget.monthly_cost_usd_limit = (
        Decimal(str(data.monthly_cost_usd_limit))
        if data.monthly_cost_usd_limit is not None
        else None
    )
    budget.monthly_task_limit = data.monthly_task_limit
    budget.enabled = data.enabled
    await db.flush()
    await db.refresh(budget)
    return budget


async def usage_snapshot(db: AsyncSession, tenant_id: uuid.UUID) -> UsageSnapshot:
    """Current-month consumption vs the tenant's caps (RLS-scoped).

    ``cost_usd`` is the attributed cost of every run (real token count × registry
    price), which is what the cost cap enforces, so the gate is demonstrable even
    offline. ``real_cost_usd`` is the subset from truly-paid providers — surfaced
    separately so a STUB run is never dressed up as real spend.
    """
    # now() is stable within the transaction, so the gate's WHERE uses the same month.
    period = (await db.execute(select(func.date_trunc("month", func.now())))).scalar_one()
    stmt = select(
        func.coalesce(func.sum(UsageRecord.cost_usd), 0),
        func.coalesce(
            func.sum(case((UsageRecord.provider_is_real, UsageRecord.cost_usd), else_=0)), 0
        ),
        func.coalesce(func.sum(UsageRecord.input_tokens), 0),
        func.coalesce(func.sum(UsageRecord.output_tokens), 0),
        func.count(),
    ).where(
        UsageRecord.tenant_id == tenant_id,  # defense-in-depth on top of RLS
        UsageRecord.created_at >= func.date_trunc("month", func.now()),
    )
    cost, real_cost, in_tok, out_tok, n_tasks = (await db.execute(stmt)).one()

    budget = await get_budget(db, tenant_id)
    cost_limit = (
        float(budget.monthly_cost_usd_limit)
        if budget is not None and budget.monthly_cost_usd_limit is not None
        else None
    )
    task_limit = budget.monthly_task_limit if budget is not None else None
    enabled = bool(budget.enabled) if budget is not None else False

    cost_f = float(cost)
    n = int(n_tasks)
    return UsageSnapshot(
        period_start=period,
        cost_usd=cost_f,
        real_cost_usd=float(real_cost),
        input_tokens=int(in_tok),
        output_tokens=int(out_tok),
        n_tasks=n,
        monthly_cost_usd_limit=cost_limit,
        monthly_task_limit=task_limit,
        enabled=enabled,
        cost_remaining_usd=max(0.0, cost_limit - cost_f) if cost_limit is not None else None,
        tasks_remaining=max(0, task_limit - n) if task_limit is not None else None,
    )


async def check_budget(db: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Pre-run gate. Raises HTTP 402 when an enabled cap is reached; else no-op."""
    snap = await usage_snapshot(db, tenant_id)
    reason = budget_breach(
        enabled=snap.enabled,
        cost_limit=snap.monthly_cost_usd_limit,
        task_limit=snap.monthly_task_limit,
        cost_used=snap.cost_usd,
        tasks_used=snap.n_tasks,
    )
    if reason is not None:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)


async def record_usage(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    execution_id: uuid.UUID | None,
    created_by: uuid.UUID | None,
    cost_usd: float,
    input_tokens: int,
    output_tokens: int,
    provider_is_real: bool,
) -> None:
    """Append one metering row for a succeeded run (single persistence path)."""
    db.add(
        UsageRecord(
            tenant_id=tenant_id,
            execution_id=execution_id,
            created_by=created_by,
            cost_usd=Decimal(str(cost_usd)),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider_is_real=provider_is_real,
        )
    )

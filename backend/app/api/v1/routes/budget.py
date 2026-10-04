"""Budget + usage — per-tenant cost/volume caps and current consumption.

``GET /v1/budget`` and ``GET /v1/usage`` are readable by any authenticated member;
``PUT /v1/budget`` is admin-only (setting the org's own caps). Everything is
tenant-scoped (RLS) and the tenant is always taken from the token, never the body.
See the ``kompilo-rls`` skill.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, OrgAdmin, TenantSession, get_current_user
from app.schemas.budget import BudgetRead, BudgetUpdate, UsageSnapshot
from app.services import budget as budget_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/budget", response_model=BudgetRead, summary="Read the tenant's budget caps")
async def read_budget(user: CurrentUser, db: TenantSession) -> BudgetRead:
    budget = await budget_service.get_budget(db, user.tenant_id)
    if budget is None:
        # No row = unlimited / enforcement off.
        return BudgetRead(monthly_cost_usd_limit=None, monthly_task_limit=None, enabled=False)
    return BudgetRead.model_validate(budget)


@router.put("/budget", response_model=BudgetRead, summary="Set the tenant's budget caps (admin)")
async def set_budget(payload: BudgetUpdate, admin: OrgAdmin, db: TenantSession) -> BudgetRead:
    budget = await budget_service.upsert_budget(
        db, admin.tenant_id, created_by=admin.id, data=payload
    )
    return BudgetRead.model_validate(budget)


@router.get("/usage", response_model=UsageSnapshot, summary="Current-month usage vs caps")
async def read_usage(user: CurrentUser, db: TenantSession) -> UsageSnapshot:
    return await budget_service.usage_snapshot(db, user.tenant_id)

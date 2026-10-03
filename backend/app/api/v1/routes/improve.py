"""POST /v1/improve/loop — iterate a task toward a measured quality target (V1.5 #1).

Authenticated + tenant-scoped (the loop executes through the Gateway, whose cache is keyed
by tenant). Stateless: it persists nothing — it compiles, measures (Evaluator ``rules-v1``)
and folds the Improver's grounded suggestions into the quality contract, iterating until
the measured score reaches the target, converges, has nothing left to fold, or hits
``max_iterations``. With no provider key the offline Echo STUB runs and the result is
flagged ``provider_is_real=false``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, get_current_user
from app.engines.improve_loop import ImproveLoop
from app.schemas.benchmark import ImprovementLoopRequest, ImprovementLoopResult

router = APIRouter(dependencies=[Depends(get_current_user)])
_loop = ImproveLoop()


@router.post(
    "/improve/loop",
    response_model=ImprovementLoopResult,
    summary="Iteratively improve a task from grounded signals, re-measuring each round",
)
async def improve_loop(payload: ImprovementLoopRequest, user: CurrentUser) -> ImprovementLoopResult:
    return await _loop.run(
        task=payload.task,
        cases=payload.cases,
        mode=payload.mode,
        output_format=payload.output_format,
        target_model=payload.target_model,
        quality_contract=payload.quality_contract,
        max_iterations=payload.max_iterations,
        target_score=payload.target_score,
        tenant_id=str(user.tenant_id),
    )

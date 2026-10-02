"""Compile endpoint: turn an intent into an execution strategy (STUB stages).

NOTE: unauthenticated for bootstrap. Once the stages are real this MUST be
moved behind the tenant-scoped dependency (see ``app.api.deps.TenantSession``).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.engines.pipeline import pipeline
from app.schemas.compile import CompileRequest, CompileResponse, StageTrace

router = APIRouter()


@router.post("/compile", response_model=CompileResponse, summary="Compile an intent")
async def compile_intent(payload: CompileRequest) -> CompileResponse:
    """Run the Kompilo pipeline.

    Stages are STUB implementations — the response carries ``is_stub=true``.
    """
    ctx = await pipeline.run(payload.intent, payload.context)
    return CompileResponse(
        intent=ctx.intent,
        strategy=ctx.artifacts,
        trace=[StageTrace(stage=r.stage, status=r.status, note=r.note) for r in ctx.trace],
        is_stub=True,
    )

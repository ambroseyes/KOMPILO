"""Compile endpoint: turn an intent into an execution strategy.

The ``understand`` stage is real (it calls an LLM with tenant data), so the
endpoint is authenticated: every request requires a member (``get_current_user``),
which also pins the tenant for RLS. The remaining stages are still STUB — each
trace entry carries its own ``is_stub`` flag, and the top-level ``is_stub`` is
true while any stage is a placeholder.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.engines.pipeline import pipeline
from app.schemas.compile import CompileRequest, CompileResponse, StageTrace

# All compile routes require an authenticated member (tenant pinned for RLS).
router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/compile", response_model=CompileResponse, summary="Compile an intent")
async def compile_intent(payload: CompileRequest) -> CompileResponse:
    """Run the Kompilo pipeline.

    ``understand`` is real; later stages are STUB. ``is_stub`` reflects whether any
    stage in the trace is still a placeholder.
    """
    ctx = await pipeline.run(payload.intent, payload.context)
    trace = [
        StageTrace(stage=r.stage, status=r.status, note=r.note, is_stub=r.is_stub)
        for r in ctx.trace
    ]
    return CompileResponse(
        intent=ctx.intent,
        strategy=ctx.artifacts,
        trace=trace,
        is_stub=any(t.is_stub for t in trace),
    )

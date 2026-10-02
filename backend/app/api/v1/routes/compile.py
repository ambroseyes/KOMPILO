"""Compile endpoint: preview the pipeline for an intent (synchronous).

``understand`` is real (it may call an LLM to analyse the intent), so the endpoint
is authenticated: every request requires a member (``get_current_user``), which also
pins the tenant for RLS. The later stages are still STUB — each trace entry carries
its own ``is_stub`` flag, and the top-level ``is_stub`` is true while any stage is a
placeholder.

This is a stateless preview; it persists nothing. To run and record an execution
over a stored prompt version, use the async ``/executions`` endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.engines.pipeline import pipeline
from app.schemas.compile import CompileRequest, CompileResponse, StageTrace

router = APIRouter()


@router.post("/compile", response_model=CompileResponse, summary="Preview the pipeline")
async def compile_intent(payload: CompileRequest, user: CurrentUser) -> CompileResponse:
    """Run the Kompilo pipeline and return its trace (no persistence).

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

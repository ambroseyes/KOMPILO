"""Compile endpoint: turn a task into an execution plan + a compiled prompt.

Public and stateless (no DB, no tenant) — a pure compute endpoint for the consumer
screen. It is deterministic except for the Intent Engine's optional, cost-gated LLM
refine. Driven by ``KompiloCore`` (see the kompilo-pipeline / kompilo-intent skills).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.engines.kompilo_core import KompiloCore
from app.schemas.compile import CompileRequest, CompileResponse

router = APIRouter()
_core = KompiloCore()


@router.post(
    "/compile", response_model=CompileResponse, summary="Compile a task into a plan + prompt"
)
async def compile_task(payload: CompileRequest) -> CompileResponse:
    return await _core.compile(
        payload.task,
        target_model=payload.target_model,
        mode=payload.mode,
        output_format=payload.output_format,
        quality_contract=payload.quality_contract,
    )

"""SSE streaming of an execution: GET /v1/executions/{id}/stream.

Emits the journaled steps, then the output progressively as ``token`` events, then a
``done`` event. Auth is via a ``token`` query param (an EventSource cannot set an
Authorization header) or a Bearer header (curl); the execution is loaded tenant-scoped,
so RLS hides other tenants' executions (→ 404).

Robust close: the data is loaded up front (no DB session held open during the stream),
the generator exits cleanly on client disconnect (CancelledError), and any error is sent
as an ``error`` event before closing.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.core.tenancy import apply_tenant_guc
from app.db.session import session_scope
from app.models.execution import Execution
from app.models.execution_step import ExecutionStep
from app.telemetry.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

_CHUNK = 48


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_tenant(token: str | None) -> uuid.UUID:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        claims = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc
    tid = claims.get("tid")
    if not tid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token missing tenant")
    return uuid.UUID(str(tid))


async def _load(
    execution_id: uuid.UUID, tenant_id: uuid.UUID
) -> tuple[str, str, list[dict[str, Any]]]:
    async with session_scope() as s:
        await apply_tenant_guc(s, tenant_id)
        execution = await s.get(Execution, execution_id)
        if execution is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Execution not found")
        rows = (
            (
                await s.execute(
                    select(ExecutionStep)
                    .where(ExecutionStep.execution_id == execution_id)
                    .order_by(ExecutionStep.step_order)
                )
            )
            .scalars()
            .all()
        )
        output = execution.output if isinstance(execution.output, dict) else {}
        text = str(output.get("text", ""))
        steps = [
            {
                "order": r.step_order,
                "action": r.action,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": r.cost_usd,
                "cached": r.cached,
                "latency_ms": r.latency_ms,
            }
            for r in rows
        ]
        return execution.status, text, steps


@router.get("/executions/{execution_id}/stream", summary="Stream an execution over SSE")
async def stream_execution(
    execution_id: uuid.UUID,
    token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    bearer: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    tenant_id = _resolve_tenant(token or bearer)
    exec_status, text, steps = await _load(execution_id, tenant_id)

    async def _events() -> AsyncIterator[str]:
        try:
            for step in steps:
                yield _sse("step", step)
                await asyncio.sleep(0.005)
            for i in range(0, len(text), _CHUNK):
                yield _sse("token", {"text": text[i : i + _CHUNK]})
                await asyncio.sleep(0.01)
            yield _sse("done", {"status": exec_status, "length": len(text)})
        except asyncio.CancelledError:  # client disconnected — clean close
            raise
        except Exception:  # noqa: BLE001 — surface a terminal error event, then close
            logger.exception("stream: error while streaming execution %s", execution_id)
            yield _sse("error", {"detail": "stream error"})

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

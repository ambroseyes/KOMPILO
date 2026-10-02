"""Background tasks executed by ARQ workers."""

from __future__ import annotations

from typing import Any

from app.engines.pipeline import pipeline
from app.telemetry.logging import get_logger

logger = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    logger.info("ARQ worker starting up")


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("ARQ worker shutting down")


async def compile_intent_task(
    ctx: dict[str, Any],
    intent: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the compile pipeline off the request path (STUB stages for now)."""
    result = await pipeline.run(intent, context or {})
    return {
        "intent": result.intent,
        "artifacts": result.artifacts,
        "trace": [{"stage": r.stage, "status": r.status} for r in result.trace],
    }

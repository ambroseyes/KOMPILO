"""Pipeline orchestrator: runs ordered stages over a shared context."""

from __future__ import annotations

from typing import Any

from app.engines.base import PipelineContext, Stage, StageResult
from app.engines.stages import DEFAULT_STAGES
from app.telemetry.logging import get_logger

logger = get_logger(__name__)


class Pipeline:
    def __init__(self, stages: list[Stage] | None = None) -> None:
        self._stages = stages if stages is not None else DEFAULT_STAGES

    async def run(self, intent: str, context: dict[str, Any] | None = None) -> PipelineContext:
        ctx = PipelineContext(intent=intent, context=context or {})
        for stage in self._stages:
            try:
                result = await stage.run(ctx)
            except Exception as exc:  # noqa: BLE001 — stage isolation is intentional
                logger.exception("Stage %s failed", stage.name)
                result = StageResult(stage.name, "error", f"error: {exc}")
            ctx.trace.append(result)
            if result.status == "error":
                break
        return ctx


# Shared default instance.
pipeline = Pipeline()

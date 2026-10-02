"""Health endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.db.session import engine
from app.schemas.common import HealthResponse
from app.telemetry.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse, summary="Service health")
async def health() -> HealthResponse:
    """Report service status, version, and database reachability.

    Always returns 200 with a diagnostic body; ``status`` is ``degraded`` when
    the database is unreachable (``db: ko``).
    """
    db = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — report as ko rather than failing the probe
        logger.warning("health check: database unreachable", exc_info=True)
        db = "ko"

    return HealthResponse(status="ok" if db == "ok" else "degraded", version=__version__, db=db)


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    """Pure liveness — no external dependencies (for k8s/load balancers)."""
    return {"status": "ok"}

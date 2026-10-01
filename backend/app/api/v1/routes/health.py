"""Liveness and readiness probes."""
from __future__ import annotations

from fastapi import APIRouter, Response, status
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from app.schemas.common import HealthComponent, ReadinessResponse

router = APIRouter()


@router.get("/health/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    """Pure liveness — no external dependencies."""
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness probe", response_model=ReadinessResponse)
async def ready(response: Response) -> ReadinessResponse:
    """Readiness — verifies PostgreSQL and Redis connectivity."""
    components: list[HealthComponent] = []

    # PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        components.append(HealthComponent(name="postgres", ok=True))
    except Exception as exc:  # noqa: BLE001
        components.append(HealthComponent(name="postgres", ok=False, detail=str(exc)))

    # Redis
    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.ping()
        components.append(HealthComponent(name="redis", ok=True))
    except Exception as exc:  # noqa: BLE001
        components.append(HealthComponent(name="redis", ok=False, detail=str(exc)))
    finally:
        await redis.aclose()

    all_ok = all(c.ok for c in components)
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ok" if all_ok else "degraded", components=components)

"""ARQ task queue — enqueue background jobs from the request path.

The API creates an ``executions`` row (status ``pending``) and enqueues a job; an
ARQ worker (``app.workers``) runs it and updates the row. The enqueue happens from a
FastAPI ``BackgroundTasks`` callback that runs AFTER the request transaction commits,
so the worker never races the row's creation.

The Redis pool is created lazily and cached. Tests reset it between cases (its
connection is bound to the event loop that created it) via ``close_arq_pool``.
"""

from __future__ import annotations

import uuid

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

#: Must match the function name registered in ``app.workers.settings.WorkerSettings``.
UNDERSTAND_TASK = "run_understand_task"

_pool: ArqRedis | None = None


def get_redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(get_redis_settings())
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue_understand(execution_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Enqueue the understand job. Worker args are strings (JSON-serializable)."""
    pool = await get_arq_pool()
    await pool.enqueue_job(UNDERSTAND_TASK, str(execution_id), str(tenant_id))

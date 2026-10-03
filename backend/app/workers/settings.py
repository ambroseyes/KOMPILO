"""ARQ worker configuration.

Run with:  arq app.workers.settings.WorkerSettings
"""

from __future__ import annotations

from arq.connections import RedisSettings

from app.core.config import settings
from app.telemetry.logging import configure_logging
from app.workers.tasks import run_pipeline_task, shutdown, startup

configure_logging()


class WorkerSettings:
    functions = [run_pipeline_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

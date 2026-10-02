"""ARQ worker configuration.

Run with:  arq app.workers.settings.WorkerSettings
"""

from __future__ import annotations

from arq.connections import RedisSettings

from app.core.config import settings
from app.telemetry.logging import configure_logging
from app.workers.tasks import compile_intent_task, run_understand_task, shutdown, startup

configure_logging()


class WorkerSettings:
    functions = [compile_intent_task, run_understand_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

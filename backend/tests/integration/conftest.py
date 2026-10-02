"""Integration-test fixtures.

pytest-asyncio gives each test its own event loop, but the app's async engine is
created once at import and pools connections bound to the loop that first used
them. Disposing the pool around every test guarantees each one gets fresh
connections on its own loop (otherwise tests after the first fail or skip).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from app.core.queue import close_arq_pool
from app.core.redis import close_redis
from app.db.session import engine


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_pool() -> AsyncIterator[None]:
    await engine.dispose()
    await close_arq_pool()
    await close_redis()
    yield
    await engine.dispose()
    await close_arq_pool()
    await close_redis()

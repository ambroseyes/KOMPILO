"""Shared async Redis client (Gateway semantic cache, idempotency, SSE).

A single lazily-created client with a connection pool. Tests reset it between cases
(the client binds to the event loop that first used it) via ``close_redis``.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(settings.redis_url)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None

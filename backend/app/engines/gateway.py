"""Kompilo Gateway — the single exit point to models.

Responsibilities:
- **Semantic cache** (Redis): fingerprint = sha256(tenant + normalized request). A hit
  returns the stored answer with ZERO new cost/tokens (``cached=True``).
- **Retries + backoff** per model, then **fallback** to the next model in the route.
- **Tracing**: tokens / cost / latency, logged WITHOUT the prompt content or any secret.

Cost is REAL: computed from the actual token usage × the registry's per-token prices
(0 on a cache hit, and 0 when the model is not priced in the registry).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.config import settings
from app.core.redis import get_redis
from app.engines.providers import LLMProvider, ProviderError, get_execution_provider
from app.engines.registry import default_registry
from app.schemas.registry import ModelCapability
from app.telemetry.logging import get_logger

logger = get_logger(__name__)

_WS_RE = re.compile(r"\s+")


class GatewayError(RuntimeError):
    """All models failed after retries/fallback."""


@dataclass(frozen=True, slots=True)
class GatewayResponse:
    text: str
    model: str
    provider: str
    provider_is_real: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float  # REAL cost (0 on cache hit / unpriced model)
    latency_ms: int
    cached: bool
    attempts: int
    fallback_used: bool


def _fingerprint(tenant_id: str, system: str | None, prompt: str, json_mode: bool) -> str:
    # Normalized request + tenant (model-agnostic, per the cache contract).
    norm = _WS_RE.sub(" ", f"{system or ''}\n{prompt}".strip().lower())
    raw = f"{tenant_id}|{int(json_mode)}|{norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _price(registry: Sequence[ModelCapability], model: str, in_tok: int, out_tok: int) -> float:
    entry = next((m for m in registry if m.model == model), None)
    if entry is None:
        return 0.0  # unpriced model (e.g. a local/stub model not in the registry)
    return round(in_tok / 1_000_000 * entry.cost_in + out_tok / 1_000_000 * entry.cost_out, 6)


class Gateway:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        registry: Sequence[ModelCapability] | None = None,
        redis: Redis | None = None,
    ) -> None:
        self._provider = provider or get_execution_provider()
        self._registry = tuple(registry) if registry is not None else default_registry()
        # Best-effort cache; if Redis is down, caching is silently skipped.
        self._redis = redis if redis is not None else get_redis()

    async def _cache_get(self, key: str) -> dict[str, object] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
        except Exception:  # noqa: BLE001 — cache is best-effort
            return None
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except ValueError:
            return None

    async def _cache_set(self, key: str, value: dict[str, object]) -> None:
        if self._redis is None or settings.gateway_cache_ttl_seconds <= 0:
            return
        try:
            await self._redis.set(key, json.dumps(value), ex=settings.gateway_cache_ttl_seconds)
        except Exception:  # noqa: BLE001 — cache is best-effort
            logger.warning("gateway: cache set failed (ignored)")

    async def complete(
        self,
        *,
        tenant_id: str,
        model_ids: Sequence[str],
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> GatewayResponse:
        caps = self._provider.capabilities()
        fingerprint = _fingerprint(tenant_id, system, prompt, json_mode)
        cache_key = f"komp:cache:{tenant_id}:{fingerprint}"

        cached = await self._cache_get(cache_key)
        if cached is not None:
            logger.info("gateway: cache hit fp=%s", fingerprint[:12])
            return GatewayResponse(
                text=str(cached.get("text", "")),
                model=str(cached.get("model", "")),
                provider=str(cached.get("provider", caps.provider)),
                provider_is_real=caps.is_real,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,  # served from cache → no new cost
                latency_ms=0,
                cached=True,
                attempts=0,
                fallback_used=False,
            )

        candidates = [m for m in model_ids if m] or [settings.execution_llm_model]
        attempts = 0
        last_error: Exception | None = None
        for index, model in enumerate(candidates):
            for _ in range(max(1, settings.gateway_max_attempts_per_model)):
                attempts += 1
                started = time.perf_counter()
                try:
                    result = await self._provider.complete(
                        model=model,
                        prompt=prompt,
                        system=system,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        json_mode=json_mode,
                    )
                except ProviderError as exc:
                    last_error = exc
                    await asyncio.sleep(settings.gateway_backoff_base_seconds * attempts)
                    continue
                latency_ms = int((time.perf_counter() - started) * 1000)
                cost = _price(
                    self._registry, result.model, result.input_tokens, result.output_tokens
                )
                await self._cache_set(
                    cache_key,
                    {
                        "text": result.text,
                        "model": result.model,
                        "provider": result.provider,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "cost_usd": cost,
                    },
                )
                logger.info(
                    "gateway: ok model=%s provider=%s in=%d out=%d cost=%.6f latency_ms=%d "
                    "attempts=%d fallback=%s real=%s",
                    result.model,
                    result.provider,
                    result.input_tokens,
                    result.output_tokens,
                    cost,
                    latency_ms,
                    attempts,
                    index > 0,
                    caps.is_real,
                )
                return GatewayResponse(
                    text=result.text,
                    model=result.model,
                    provider=result.provider,
                    provider_is_real=caps.is_real,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    cached=False,
                    attempts=attempts,
                    fallback_used=index > 0,
                )

        raise GatewayError(
            f"all {len(candidates)} model(s) failed after {attempts} attempts"
        ) from last_error

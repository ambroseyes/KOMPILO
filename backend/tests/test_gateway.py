"""No-DB unit tests for the Gateway: semantic cache, tenant scoping, retry→fallback."""

from __future__ import annotations

from datetime import date

import pytest

from app.engines.gateway import Gateway
from app.engines.providers.base import CompletionResult, ProviderCapabilities, ProviderError
from app.schemas.registry import ModelCapability


class _CountingProvider:
    name = "counter"

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("counter", supports_streaming=False, is_real=True)

    async def complete(self, *, model: str, prompt: str, **_: object) -> CompletionResult:
        self.calls += 1
        return CompletionResult(f"answer-{self.calls}", 100, 50, model, self.name)


class _FlakyProvider:
    name = "flaky"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("flaky", supports_streaming=False, is_real=True)

    async def complete(self, *, model: str, prompt: str, **_: object) -> CompletionResult:
        self.seen.append(model)
        if model == "m1":
            raise ProviderError("m1 down")
        return CompletionResult("ok", 10, 5, model, self.name)


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


def _registry() -> list[ModelCapability]:
    def m(name: str, ci: float, co: float) -> ModelCapability:
        return ModelCapability(
            model=name,
            provider="p",
            context_window=8000,
            supports_tools=True,
            supports_vision=True,
            structured_output=True,
            reasoning_strength="medium",
            cost_in=ci,
            cost_out=co,
            latency_ms=100,
            last_verified=date(2026, 1, 1),
        )

    return [m("m1", 1.0, 2.0), m("m2", 0.5, 1.0)]


@pytest.mark.asyncio
async def test_gateway_caches_second_identical_call() -> None:
    provider = _CountingProvider()
    gw = Gateway(provider=provider, registry=_registry(), redis=_FakeRedis())  # type: ignore[arg-type]

    r1 = await gw.complete(tenant_id="t1", model_ids=["m1"], prompt="hello world")
    assert provider.calls == 1
    assert r1.cached is False and r1.cost_usd > 0

    r2 = await gw.complete(tenant_id="t1", model_ids=["m1"], prompt="hello world")
    assert provider.calls == 1  # served from cache — provider NOT called again
    assert r2.cached is True
    assert r2.cost_usd == 0.0  # no new cost
    assert r2.text == r1.text


@pytest.mark.asyncio
async def test_gateway_cache_is_tenant_scoped() -> None:
    provider = _CountingProvider()
    gw = Gateway(provider=provider, registry=_registry(), redis=_FakeRedis())  # type: ignore[arg-type]
    await gw.complete(tenant_id="t1", model_ids=["m1"], prompt="same prompt")
    await gw.complete(tenant_id="t2", model_ids=["m1"], prompt="same prompt")
    assert provider.calls == 2  # different tenant → different fingerprint → miss


@pytest.mark.asyncio
async def test_gateway_retries_then_falls_back() -> None:
    provider = _FlakyProvider()
    gw = Gateway(provider=provider, registry=_registry(), redis=_FakeRedis())  # type: ignore[arg-type]
    resp = await gw.complete(tenant_id="t1", model_ids=["m1", "m2"], prompt="x")
    assert resp.model == "m2"
    assert resp.fallback_used is True
    assert provider.seen == ["m1", "m1", "m2"]  # 2 attempts on m1, then m2 succeeds

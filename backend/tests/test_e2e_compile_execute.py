"""E2E (deterministic, no DB): compile → execute → result, with a MOCKED provider.

Uses Kompilo Core to compile a real task, then runs the plan through the Executor over a
Gateway backed by a fake in-memory provider + redis — so there is no network, no LLM key,
and the result is fully deterministic. Also covers the JSON repair stage.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.engines.executor import Executor
from app.engines.gateway import Gateway
from app.engines.kompilo_core import KompiloCore
from app.engines.providers.base import CompletionResult, ProviderCapabilities
from app.engines.verifier import verify_output
from app.schemas.compile import CostEstimate, ExecutionPlan, ExecutionStep
from app.schemas.registry import ModelCapability


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


class _GreetingProvider:
    name = "fake-real"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("fake-real", supports_streaming=False, is_real=True)

    async def complete(self, *, model: str, prompt: str, **_: object) -> CompletionResult:
        return CompletionResult("Bonjour et bienvenue chez nous !", 120, 20, model, self.name)


class _JsonRepairProvider:
    """Returns invalid JSON first, then valid JSON once the repair instruction appears."""

    name = "fake-json"

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("fake-json", supports_streaming=False, is_real=True)

    async def complete(self, *, model: str, prompt: str, **_: object) -> CompletionResult:
        self.calls += 1
        if "JSON valide" in prompt:  # the repair re-prompt
            return CompletionResult('{"ok": true}', 10, 5, model, self.name)
        return CompletionResult("voici: {ok: true", 10, 5, model, self.name)  # invalid JSON


def _registry() -> list[ModelCapability]:
    return [
        ModelCapability(
            model="gpt-4o-mini",
            provider="p",
            context_window=8000,
            supports_tools=True,
            supports_vision=True,
            structured_output=True,
            reasoning_strength="medium",
            cost_in=0.15,
            cost_out=0.6,
            latency_ms=100,
            last_verified=date(2026, 1, 1),
        )
    ]


@pytest.mark.asyncio
async def test_compile_then_execute_produces_a_result() -> None:
    response, _catr = await KompiloCore().compile_with_catr(
        "Rédige un message de bienvenue chaleureux pour un nouveau client"
    )
    assert response.execution_plan is not None  # PROCEED
    assert response.compiled_prompt is not None

    gw = Gateway(provider=_GreetingProvider(), registry=_registry(), redis=_FakeRedis())  # type: ignore[arg-type]
    outcome = await Executor(gateway=gw).run(
        plan=response.execution_plan,
        compiled_prompt=response.compiled_prompt.text,
        tenant_id="t-e2e",
    )

    assert outcome.output == "Bonjour et bienvenue chez nous !"
    assert outcome.provider_is_real is True
    assert outcome.steps and outcome.steps[0].output
    assert outcome.total_cost_usd >= 0.0
    # The result verifies as a non-empty markdown output.
    assert verify_output(outcome.output, output_format="markdown").valid is True


@pytest.mark.asyncio
async def test_execute_repairs_invalid_json() -> None:
    provider = _JsonRepairProvider()
    gw = Gateway(provider=provider, registry=_registry(), redis=_FakeRedis())  # type: ignore[arg-type]
    plan = ExecutionPlan(
        strategy="single",
        target_model="gpt-4o-mini",
        fallback_models=[],
        steps=[ExecutionStep(order=1, action="generate", detail="produce json")],
        cost=CostEstimate(input_tokens_est=0, output_tokens_est=0, cost_usd_est=0.0),
    )
    outcome = await Executor(gateway=gw).run(
        plan=plan, compiled_prompt="Donne un objet JSON", tenant_id="t-json", json_mode=True
    )

    assert provider.calls == 2  # first attempt invalid → one repair attempt
    assert outcome.steps[0].repaired is True
    assert verify_output(outcome.output, output_format="json").valid is True

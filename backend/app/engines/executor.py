"""Executor v1 — run an execution plan step by step through the Gateway.

Each step is dispatched to the Gateway (which handles caching, retries, fallback and
cost). The outcome carries a per-step record (input, output, tokens, REAL cost, cached,
latency) that the route persists into ``execution_steps``. A ``retrieve`` step is a
STUB for now (no corpus wired) — clearly marked, zero cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.engines.gateway import Gateway
from app.schemas.compile import ExecutionPlan


@dataclass(frozen=True, slots=True)
class StepOutcome:
    order: int
    action: str
    input_prompt: str
    output: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    cached: bool
    latency_ms: int


@dataclass
class ExecutionOutcome:
    output: str
    steps: list[StepOutcome] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    provider: str = "unknown"
    provider_is_real: bool = False
    cached_any: bool = False


_RETRIEVAL_STUB = "[retrieval STUB — no corpus configured in v1]"


class Executor:
    def __init__(self, gateway: Gateway | None = None) -> None:
        self._gateway = gateway or Gateway()

    async def run(
        self,
        *,
        plan: ExecutionPlan,
        compiled_prompt: str,
        tenant_id: str,
        system: str | None = None,
        json_mode: bool = False,
    ) -> ExecutionOutcome:
        model_ids = [m for m in [plan.target_model, *plan.fallback_models] if m]
        outcome = ExecutionOutcome(output="")
        last_text = ""

        for step in plan.steps:
            if step.action == "retrieve":
                outcome.steps.append(
                    StepOutcome(
                        order=step.order,
                        action=step.action,
                        input_prompt=step.detail,
                        output=_RETRIEVAL_STUB,
                        input_tokens=0,
                        output_tokens=0,
                        cost_usd=0.0,
                        model="-",
                        cached=False,
                        latency_ms=0,
                    )
                )
                continue

            prompt = compiled_prompt
            if step.order > 1:
                prompt = f"{compiled_prompt}\n\nFocus on this step: {step.detail}"

            resp = await self._gateway.complete(
                tenant_id=tenant_id,
                model_ids=model_ids,
                prompt=prompt,
                system=system,
                json_mode=json_mode,
            )
            outcome.steps.append(
                StepOutcome(
                    order=step.order,
                    action=step.action,
                    input_prompt=prompt,
                    output=resp.text,
                    input_tokens=resp.input_tokens,
                    output_tokens=resp.output_tokens,
                    cost_usd=resp.cost_usd,
                    model=resp.model,
                    cached=resp.cached,
                    latency_ms=resp.latency_ms,
                )
            )
            outcome.total_input_tokens += resp.input_tokens
            outcome.total_output_tokens += resp.output_tokens
            outcome.total_cost_usd = round(outcome.total_cost_usd + resp.cost_usd, 6)
            outcome.total_latency_ms += resp.latency_ms
            outcome.provider = resp.provider
            outcome.provider_is_real = resp.provider_is_real
            outcome.cached_any = outcome.cached_any or resp.cached
            last_text = resp.text

        outcome.output = last_text
        return outcome

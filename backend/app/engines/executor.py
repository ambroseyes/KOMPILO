"""Executor v1 — run an execution plan step by step through the Gateway.

Each step is dispatched to the Gateway (which handles caching, retries, fallback and
cost). The outcome carries a per-step record (input, output, tokens, REAL cost, cached,
latency) that the route persists into ``execution_steps``. A ``retrieve`` step is a
STUB for now (no corpus wired) — clearly marked, zero cost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.core.errors import KompiloError
from app.engines.gateway import Gateway, GatewayResponse
from app.engines.retriever import RetrievalResult, Retriever
from app.schemas.compile import ExecutionPlan


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


_REPAIR_INSTRUCTION = (
    "\n\nLa réponse précédente n'était pas un JSON valide. "
    "Renvoie UNIQUEMENT un objet JSON valide, sans texte ni balises autour."
)


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
    repaired: bool = False  # True if a JSON repair retry was applied to this step


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
_MAX_CONTEXT_CHARS = 4000


def _format_context(result: RetrievalResult) -> str:
    """Join retrieved chunks into a bounded, labelled context block for the prompt."""
    blocks: list[str] = []
    budget = _MAX_CONTEXT_CHARS
    for i, chunk in enumerate(result.chunks, start=1):
        snippet = chunk.content[:budget]
        blocks.append(f"[{i}] {chunk.document_title}\n{snippet}")
        budget -= len(snippet)
        if budget <= 0:
            break
    return "\n\n".join(blocks)


def _format_retrieval_output(result: RetrievalResult) -> str:
    """Human-readable record of what retrieval found (journaled as the step output)."""
    if not result.chunks:
        return "[retrieval — aucun passage trouvé dans le corpus du tenant]"
    lines = [
        f"[{i}] {c.document_title} (score={c.score}) — {c.content[:160]}"
        for i, c in enumerate(result.chunks, start=1)
    ]
    header = "Passages récupérés" + ("" if result.is_real else f" — {result.note}")
    return header + ":\n" + "\n".join(lines)


class Executor:
    def __init__(self, gateway: Gateway | None = None, retriever: Retriever | None = None) -> None:
        self._gateway = gateway or Gateway()
        self._retriever = retriever

    async def run(
        self,
        *,
        plan: ExecutionPlan,
        compiled_prompt: str,
        tenant_id: str,
        system: str | None = None,
        json_mode: bool = False,
        retrieval_query: str | None = None,
    ) -> ExecutionOutcome:
        model_ids = [m for m in [plan.target_model, *plan.fallback_models] if m]
        outcome = ExecutionOutcome(output="")
        last_text = ""
        retrieved_context = ""

        for step in plan.steps:
            if step.action == "retrieve":
                output = _RETRIEVAL_STUB
                if self._retriever is not None:
                    result = await self._retriever.retrieve(retrieval_query or compiled_prompt)
                    retrieved_context = _format_context(result)
                    output = _format_retrieval_output(result)
                outcome.steps.append(
                    StepOutcome(
                        order=step.order,
                        action=step.action,
                        input_prompt=step.detail,
                        output=output,
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
            if retrieved_context:
                prompt = f"{compiled_prompt}\n\n<context>\n{retrieved_context}\n</context>"
            if step.order > 1:
                prompt = f"{prompt}\n\nFocus on this step: {step.detail}"

            resp = await self._gateway.complete(
                tenant_id=tenant_id,
                model_ids=model_ids,
                prompt=prompt,
                system=system,
                json_mode=json_mode,
            )

            # ── Repair (one attempt): a JSON contract whose output didn't parse ──────
            text = resp.text
            in_tok, out_tok = resp.input_tokens, resp.output_tokens
            cost, latency = resp.cost_usd, resp.latency_ms
            repaired = False
            if json_mode and not resp.cached and not _is_json(text):
                fix = await self._repair_json(tenant_id, model_ids, prompt, system)
                if fix is not None and _is_json(fix.text):
                    text = fix.text
                    in_tok += fix.input_tokens
                    out_tok += fix.output_tokens
                    cost = round(cost + fix.cost_usd, 6)
                    latency += fix.latency_ms
                    repaired = True

            outcome.steps.append(
                StepOutcome(
                    order=step.order,
                    action=step.action,
                    input_prompt=prompt,
                    output=text,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cost_usd=cost,
                    model=resp.model,
                    cached=resp.cached,
                    latency_ms=latency,
                    repaired=repaired,
                )
            )
            outcome.total_input_tokens += in_tok
            outcome.total_output_tokens += out_tok
            outcome.total_cost_usd = round(outcome.total_cost_usd + cost, 6)
            outcome.total_latency_ms += latency
            outcome.provider = resp.provider
            outcome.provider_is_real = resp.provider_is_real
            outcome.cached_any = outcome.cached_any or resp.cached
            last_text = text

        outcome.output = last_text
        return outcome

    async def _repair_json(
        self, tenant_id: str, model_ids: list[str], prompt: str, system: str | None
    ) -> GatewayResponse | None:
        """One corrective re-prompt asking for valid JSON. Best-effort: on any classified
        failure, return None and let the Verifier report the still-invalid output."""
        try:
            return await self._gateway.complete(
                tenant_id=tenant_id,
                model_ids=model_ids,
                prompt=prompt + _REPAIR_INSTRUCTION,
                system=system,
                json_mode=True,
            )
        except KompiloError:
            return None

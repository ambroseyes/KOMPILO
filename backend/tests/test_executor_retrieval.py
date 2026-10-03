"""Unit test: the Executor's retrieve step grounds the generate step (no DB, no network).

A fake retriever returns canned chunks and a fake gateway captures the prompt it receives.
Proves the wiring: a ``retrieve`` step injects the retrieved context into the following
``generate`` step's prompt, and journals the retrieved passages (not the old stub).
"""

from __future__ import annotations

import pytest

from app.engines.executor import _RETRIEVAL_STUB, Executor
from app.engines.gateway import GatewayResponse
from app.engines.retriever import RetrievalResult, RetrievedChunk
from app.schemas.compile import CostEstimate, ExecutionPlan, ExecutionStep


class _FakeGateway:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(self, *, tenant_id, model_ids, prompt, system=None, json_mode=False):
        self.prompts.append(prompt)
        return GatewayResponse(
            text="RÉPONSE",
            model=model_ids[0] if model_ids else "-",
            provider="fake",
            provider_is_real=False,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_ms=1,
            cached=False,
            attempts=1,
            fallback_used=False,
        )


class _FakeRetriever:
    async def retrieve(self, query, *, k=4):
        return RetrievalResult(
            chunks=[
                RetrievedChunk(
                    document_id="d1",
                    document_title="Guide Accueil",
                    chunk_id="c1",
                    chunk_index=0,
                    content="Toujours saluer le client par son prénom.",
                    score=0.91,
                )
            ],
            is_real=False,
            note="offline",
        )


def _rag_plan() -> ExecutionPlan:
    return ExecutionPlan(
        strategy="rag",
        target_model="m",
        fallback_models=[],
        steps=[
            ExecutionStep(order=1, action="retrieve", detail="Fetch sources."),
            ExecutionStep(order=2, action="generate", detail="Answer using context."),
        ],
        cost=CostEstimate(input_tokens_est=0, output_tokens_est=0, cost_usd_est=0.0),
    )


@pytest.mark.asyncio
async def test_retrieve_step_grounds_generate_step() -> None:
    gateway = _FakeGateway()
    executor = Executor(gateway=gateway, retriever=_FakeRetriever())  # type: ignore[arg-type]
    outcome = await executor.run(
        plan=_rag_plan(),
        compiled_prompt="Rédige un message de bienvenue.",
        tenant_id="t1",
        retrieval_query="bienvenue client",
    )

    retrieve_step = next(s for s in outcome.steps if s.action == "retrieve")
    assert retrieve_step.output != _RETRIEVAL_STUB
    assert "Guide Accueil" in retrieve_step.output

    # The generate step's prompt carried the retrieved context.
    assert gateway.prompts, "the generate step should have called the gateway"
    assert "<context>" in gateway.prompts[0]
    assert "saluer le client par son prénom" in gateway.prompts[0]


@pytest.mark.asyncio
async def test_retrieve_step_falls_back_to_stub_without_retriever() -> None:
    executor = Executor(gateway=_FakeGateway(), retriever=None)  # type: ignore[arg-type]
    outcome = await executor.run(plan=_rag_plan(), compiled_prompt="x", tenant_id="t1")
    retrieve_step = next(s for s in outcome.steps if s.action == "retrieve")
    assert retrieve_step.output == _RETRIEVAL_STUB

"""Kompilo Core — orchestrate the deterministic compile pipeline end to end.

intent → ambiguity → (ASK ⇒ stop & return questions | PROCEED) → complexity → strategy
→ router → prompt_compiler, assembling an execution plan, a multidimensional explainable
diagnostic, and ESTIMATED costs.

The core is deterministic except for the Intent Engine's optional, cost-gated LLM refine
(reflected in ``metadata.llm_used`` / ``deterministic``).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.engines.ambiguity import AmbiguityEngine
from app.engines.complexity import ComplexityEngine
from app.engines.diagnostics import DiagnosticEngine
from app.engines.intent import IntentEngine
from app.engines.prompt_compiler import PromptCompiler
from app.engines.registry import default_registry
from app.engines.router import ModelRouter
from app.engines.strategy import StrategyEngine
from app.schemas.catr import CanonicalAITask
from app.schemas.compile import (
    CompiledPrompt,
    CompileMetadata,
    CompileMode,
    CompileResponse,
    CostEstimate,
    ExecutionPlan,
    ExecutionStep,
    PromptRenders,
    UnderstoodIntent,
)
from app.schemas.registry import ModelCapability
from app.schemas.strategize import ComplexityAssessment, Strategy

_OUTPUT_TOKENS_EST: dict[str, int] = {
    "simple": 300,
    "moderate": 800,
    "complex": 1500,
    "agentic": 2500,
}


def _resolve_target(
    registry: Sequence[ModelCapability], target_model: str | None, primary: str | None
) -> ModelCapability | None:
    wanted = target_model or primary
    if wanted is None:
        return None
    return next((m for m in registry if m.model == wanted), None)


def _estimate_cost(
    prompt_text: str, task: str, level: str, profile: ModelCapability | None
) -> CostEstimate:
    input_tokens = (len(prompt_text) + len(task)) // 4  # ~4 chars per token
    output_tokens = _OUTPUT_TOKENS_EST.get(level, 800)
    if profile is None:
        return CostEstimate(
            input_tokens_est=input_tokens,
            output_tokens_est=output_tokens,
            cost_usd_est=0.0,
            disclaimer="No target model resolved; cost cannot be estimated.",
        )
    cost = input_tokens / 1_000_000 * profile.cost_in + output_tokens / 1_000_000 * profile.cost_out
    return CostEstimate(
        input_tokens_est=input_tokens,
        output_tokens_est=output_tokens,
        cost_usd_est=round(cost, 6),
    )


def _build_steps(strategy: Strategy, catr: CanonicalAITask) -> list[ExecutionStep]:
    if strategy.kind == "rag":
        return [
            ExecutionStep(
                order=1, action="retrieve", detail="Fetch and ground on the referenced source(s)."
            ),
            ExecutionStep(order=2, action="generate", detail="Answer using the retrieved context."),
        ]
    if strategy.kind == "chain" and catr.sub_goals:
        return [
            ExecutionStep(order=i, action="step", detail=goal)
            for i, goal in enumerate(catr.sub_goals, start=1)
        ]
    return [
        ExecutionStep(order=1, action="generate", detail="Single model call for the objective.")
    ]


class KompiloCore:
    def __init__(self, registry: Sequence[ModelCapability] | None = None) -> None:
        self._registry: tuple[ModelCapability, ...] = (
            tuple(registry) if registry is not None else default_registry()
        )
        self._router = ModelRouter(self._registry)

    async def compile(
        self,
        task: str,
        *,
        target_model: str | None = None,
        mode: CompileMode = "professional",
        output_format: str = "markdown",
        quality_contract: list[str] | None = None,
    ) -> CompileResponse:
        """Compile a task into a plan + prompt (the public, stateless result)."""
        response, _catr = await self.compile_with_catr(
            task,
            target_model=target_model,
            mode=mode,
            output_format=output_format,
            quality_contract=quality_contract,
        )
        return response

    async def compile_with_catr(
        self,
        task: str,
        *,
        target_model: str | None = None,
        mode: CompileMode = "professional",
        output_format: str = "markdown",
        quality_contract: list[str] | None = None,
    ) -> tuple[CompileResponse, CanonicalAITask]:
        """Like :meth:`compile`, but also returns the CATR so callers that persist a
        version (the Version Manager) can snapshot it without re-running the pipeline."""
        quality_contract = quality_contract or []

        catr = await IntentEngine().run(task)
        ambiguity = AmbiguityEngine().analyze(catr)
        llm_used = catr.meta.enriched_by_llm
        understood = UnderstoodIntent(objective=catr.objective, domain=catr.domain)

        # ── ASK branch: stop before planning; return the critical questions. ─────────
        if ambiguity.decision == "ASK":
            return (
                CompileResponse(
                    understood=understood,
                    execution_plan=None,
                    compiled_prompt=None,
                    renders=None,
                    diagnostics=DiagnosticEngine().assess(
                        catr, ambiguity, output_format=output_format
                    ),
                    questions=ambiguity.questions,
                    metadata=CompileMetadata(
                        deterministic=not llm_used,
                        llm_used=llm_used,
                        target_model=None,
                        notes=["Clarification required before compiling (critical gaps)."],
                    ),
                ),
                catr,
            )

        # ── PROCEED branch: full plan + compiled prompt. ─────────────────────────────
        complexity: ComplexityAssessment = ComplexityEngine().assess(catr)
        strategy = StrategyEngine().decide(catr, complexity)
        route = self._router.route(catr, strategy, complexity)
        profile = _resolve_target(self._registry, target_model, route.primary)

        renders: PromptRenders
        compiled: CompiledPrompt
        renders, compiled = PromptCompiler().compile(
            catr, profile, mode=mode, output_format=output_format, quality_contract=quality_contract
        )

        diagnostics = DiagnosticEngine().assess(
            catr,
            ambiguity,
            complexity=complexity,
            strategy=strategy,
            route=route,
            output_format=output_format,
        )

        plan = ExecutionPlan(
            strategy=strategy.kind,
            target_model=profile.model if profile is not None else None,
            fallback_models=route.fallbacks,
            steps=_build_steps(strategy, catr),
            cost=_estimate_cost(compiled.text, task, complexity.level, profile),
        )

        notes: list[str] = []
        if profile is None:
            notes.append("No model met the required capabilities; prompt rendered generically.")
        if target_model is not None and (profile is None or profile.model != route.primary):
            notes.append(
                f"Target model '{target_model}' forced (router primary was {route.primary})."
            )

        return (
            CompileResponse(
                understood=understood,
                execution_plan=plan,
                compiled_prompt=compiled,
                renders=renders,
                diagnostics=diagnostics,
                questions=[],
                metadata=CompileMetadata(
                    deterministic=not llm_used,
                    llm_used=llm_used,
                    target_model=plan.target_model,
                    notes=notes,
                ),
            ),
            catr,
        )

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
from app.engines.contract import ContractEngine, scope_prompt_lines, success_prompt_lines
from app.engines.diagnostics import DiagnosticEngine
from app.engines.evidence import EvidenceEngine
from app.engines.execution_strategy import ExecutionStrategyEngine, approach_prompt_lines
from app.engines.intent import IntentEngine
from app.engines.prompt_compiler import PromptCompiler
from app.engines.prompt_repair import repair as repair_prompt
from app.engines.prompt_review import review as review_prompt
from app.engines.prompt_scorer import composite, score_dimensions
from app.engines.registry import default_registry
from app.engines.router import ModelRouter
from app.engines.security import SecurityEngine
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
from app.schemas.evidence import EvidenceReport
from app.schemas.execution_strategy import ExecutionStrategy
from app.schemas.prompt_quality import PromptQualityReport
from app.schemas.registry import ModelCapability
from app.schemas.security import SecurityReport
from app.schemas.strategize import AmbiguityReport, ComplexityAssessment, RouteDecision, Strategy
from app.schemas.task_contract import TaskContract

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


_BAND_FR: dict[str, str] = {
    "insufficient": "insuffisant",
    "usable": "utilisable",
    "strong": "solide",
    "execution_ready": "prêt à exécuter",
}
_PQS_NOTE = (
    "Score de *readiness* du prompt (à quel point la tâche est bien spécifiée), pas une "
    "garantie d'exactitude de la réponse. Seuils à recalibrer sur des données réelles."
)


def _assess_prompt_quality(
    *,
    catr: CanonicalAITask,
    compiled: CompiledPrompt,
    route: RouteDecision,
    complexity: ComplexityAssessment,
    profile: ModelCapability | None,
    ambiguity: AmbiguityReport,
    output_format: str,
    quality_contract: list[str],
) -> PromptQualityReport:
    """Score (PQS), adversarially review and — when below the gate — repair the prompt."""
    dims = score_dimensions(
        catr=catr,
        prompt_text=compiled.text,
        section_names=compiled.sections,
        route=route,
        complexity=complexity,
        profile=profile,
        ambiguity=ambiguity,
        output_format=output_format,
        quality_contract=quality_contract,
    )
    pqs, band, gate_passed = composite(dims)
    findings = review_prompt(
        catr=catr,
        prompt_text=compiled.text,
        section_names=compiled.sections,
        profile=profile,
        output_format=output_format,
        quality_contract=quality_contract,
    )
    repair = None
    if not gate_passed:
        repair = repair_prompt(
            catr=catr,
            base_prompt_text=compiled.text,
            section_names=compiled.sections,
            route=route,
            complexity=complexity,
            profile=profile,
            ambiguity=ambiguity,
            output_format=output_format,
            quality_contract=quality_contract,
        )
    summary = f"PQS {pqs}/100 ({_BAND_FR[band]}), {len(findings)} point(s) d'attention"
    if repair is not None and repair.applied:
        summary += f" ; réparé {repair.pqs_before}→{repair.pqs_after}"
    return PromptQualityReport(
        pqs=pqs,
        band=band,
        gate_passed=gate_passed,
        dimensions=dims,
        findings=findings,
        repair=repair,
        summary=summary,
        note=_PQS_NOTE,
    )


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

        # Evidence & uncertainty: classify the task's material and derive the policy woven
        # into the prompt (raises the PQS evidence_discipline axis — measured below).
        evidence: EvidenceReport = EvidenceEngine().assess(catr, strategy)

        # Security: scan the raw task for injection patterns and derive the trust-boundary
        # policy woven into the prompt (treat delimited/retrieved content as data).
        security: SecurityReport = SecurityEngine().scan(task, strategy)

        # Task Contract: a model-neutral spec (scope, measurable success criteria, assumptions,
        # validation, output + capability-based model preferences). Its scope + success_criteria
        # are woven into the prompt (raises the PQS scope_discipline + success_criteria axes).
        contract: TaskContract = ContractEngine().build(
            catr=catr,
            strategy=strategy,
            route=route,
            profile=profile,
            evidence=evidence,
            output_format=output_format,
            quality_contract=quality_contract,
        )

        # Execution Strategy: decomposition + recommended tactics (decompose/tool/verify/
        # ensemble). A concise "recommended approach" directive is woven in for non-trivial work.
        execution_strategy: ExecutionStrategy = ExecutionStrategyEngine().plan(
            catr=catr,
            complexity=complexity,
            strategy=strategy,
            quality_contract=quality_contract,
        )

        renders: PromptRenders
        compiled: CompiledPrompt
        renders, compiled = PromptCompiler().compile(
            catr,
            profile,
            mode=mode,
            output_format=output_format,
            quality_contract=quality_contract,
            evidence_policy=evidence.policy,
            security_policy=security.boundary_policy,
            scope_lines=scope_prompt_lines(contract),
            success_criteria_lines=success_prompt_lines(contract),
            approach_lines=approach_prompt_lines(execution_strategy),
        )
        evidence.injected = "evidence" in compiled.sections
        security.injected = "security" in compiled.sections
        execution_strategy.injected = "approach" in compiled.sections

        diagnostics = DiagnosticEngine().assess(
            catr,
            ambiguity,
            complexity=complexity,
            strategy=strategy,
            route=route,
            output_format=output_format,
        )

        prompt_quality = _assess_prompt_quality(
            catr=catr,
            compiled=compiled,
            route=route,
            complexity=complexity,
            profile=profile,
            ambiguity=ambiguity,
            output_format=output_format,
            quality_contract=quality_contract,
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
                prompt_quality=prompt_quality,
                evidence=evidence,
                security=security,
                task_contract=contract,
                execution_strategy=execution_strategy,
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

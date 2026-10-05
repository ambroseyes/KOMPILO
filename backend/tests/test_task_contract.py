"""Unit tests for the Contract Engine (deterministic; no DB, no LLM).

The contract is DERIVED from the CATR + route + evidence: scope + a standing out-of-scope
boundary, measurable success criteria, unverified assumptions, decision criteria only for a
choice, a structured output contract when the format/expected output calls for it, and a
CAPABILITY-based (never vendor-locked) model preference. The two woven line sets
(scope/success) are checked here; their PQS payoff is checked end to end in test_compile.
"""

from __future__ import annotations

from datetime import date

from app.engines.contract import ContractEngine, scope_prompt_lines, success_prompt_lines
from app.schemas.catr import CanonicalAITask, CatrMeta, MissingInformation
from app.schemas.evidence import EvidenceItem, EvidenceReport
from app.schemas.registry import ModelCapability
from app.schemas.strategize import RouteDecision, Strategy


def _catr(**kw: object) -> CanonicalAITask:
    base: dict[str, object] = dict(
        objective="Rédige une politique de sécurité réseau pour une PME",
        sub_goals=[],
        domain="general",
        inputs=[],
        context=[],
        constraints=[],
        expected_output=None,
        audience=None,
        complexity="medium",
        missing_information=[],
        ambiguities=[],
        risk="low",
        meta=CatrMeta(method="heuristic-v1", confidence=0.9, enriched_by_llm=False),
    )
    base.update(kw)
    return CanonicalAITask(**base)  # type: ignore[arg-type]


def _strategy(kind: str = "single") -> Strategy:
    return Strategy(kind=kind, rationale="t", signals=[])  # type: ignore[arg-type]


def _route(**kw: object) -> RouteDecision:
    base: dict[str, object] = dict(
        primary="gpt-4o",
        fallbacks=["claude-3-5-sonnet"],
        required_capabilities=["reasoning>=advanced"],
        rationale="t",
    )
    base.update(kw)
    return RouteDecision(**base)  # type: ignore[arg-type]


def _profile() -> ModelCapability:
    return ModelCapability(
        model="gpt-4o",
        provider="openai",
        context_window=128_000,
        supports_tools=True,
        supports_vision=True,
        structured_output=True,
        reasoning_strength="advanced",
        cost_in=2.5,
        cost_out=10.0,
        latency_ms=800,
        last_verified=date(2026, 10, 2),
    )


def _evidence(items: list[EvidenceItem] | None = None) -> EvidenceReport:
    return EvidenceReport(
        items=items or [],
        hierarchy=["a", "b", "c", "d"],
        policy=["- politique"],
        unknowns=[],
        summary="s",
        note="n",
    )


def _build(
    catr: CanonicalAITask,
    *,
    evidence: EvidenceReport | None = None,
    output_format="markdown",
    quality_contract: list[str] | None = None,
    route: RouteDecision | None = None,
):
    return ContractEngine().build(
        catr=catr,
        strategy=_strategy(),
        route=route or _route(),
        profile=_profile(),
        evidence=evidence or _evidence(),
        output_format=output_format,
        quality_contract=quality_contract or [],
    )


def test_scope_has_objective_and_a_standing_out_of_scope_boundary() -> None:
    c = _build(_catr(sub_goals=["Analyser l'existant", "Rédiger les règles"]))
    assert any("Rédige une politique" in s for s in c.scope)
    assert any("Analyser l'existant" in s for s in c.scope)
    # A standing anti-drift boundary is always present even without explicit exclusions.
    assert c.out_of_scope
    assert any("ne pas l'ajouter sans validation" in s for s in c.out_of_scope)


def test_explicit_exclusion_in_constraints_becomes_out_of_scope() -> None:
    c = _build(_catr(constraints=["Sans utiliser de service cloud payant"]))
    assert any("Exclusion énoncée" in s and "cloud" in s for s in c.out_of_scope)


def test_success_criteria_are_derived_and_mostly_measurable() -> None:
    c = _build(
        _catr(
            domain="software",
            constraints=["Compatible Python 3.12"],
            expected_output="Un module avec des tests",
            risk="high",
        ),
        quality_contract=["Couverture de tests > 90%"],
    )
    statements = [sc.statement for sc in c.success_criteria]
    # Base criterion (objective) + expected_output + constraint + software + risk + quality.
    assert any("répond à l'objectif" in s for s in statements)
    assert any("format/contenu attendu" in s for s in statements)
    assert any("Contrainte respectée" in s for s in statements)
    assert any("code s'exécute" in s for s in statements)
    assert any("effets de bord" in s for s in statements)
    assert any("Couverture de tests" in s for s in statements)
    # Every criterion carries a concrete verification, and most are machine-checkable.
    assert all(sc.verification for sc in c.success_criteria)
    assert sum(1 for sc in c.success_criteria if sc.measurable) >= 3


def test_decision_criteria_only_for_a_choice() -> None:
    plain = _build(_catr(objective="Rédige un rapport"))
    assert plain.decision_criteria is None
    choice = _build(
        _catr(objective="Choisir entre AWS et GCP", constraints=["Budget < 1000€/mois"])
    )
    assert choice.decision_criteria is not None
    assert any("1000" in c for c in choice.decision_criteria)
    # A choice without stated constraints still demands explicit criteria (honest default).
    bare_choice = _build(_catr(objective="Recommande la meilleure base de données"))
    assert bare_choice.decision_criteria is not None


def test_output_contract_structured_detection_and_model_independent() -> None:
    md = _build(_catr(), output_format="markdown")
    assert md.output_contract.structured is False
    assert md.output_contract.model_independent is True  # always portable
    js = _build(_catr(), output_format="json")
    assert js.output_contract.structured is True
    hinted = _build(
        _catr(expected_output="Un JSON avec les champs name et score"), output_format="text"
    )
    assert hinted.output_contract.structured is True
    assert hinted.output_contract.schema_hint  # expected output surfaced as a hint


def test_model_preferences_are_capability_based_not_vendor_locked() -> None:
    c = _build(_catr(), route=_route(primary="gpt-4o", fallbacks=["claude-3-5-sonnet", "qwen-2.5"]))
    mp = c.model_preferences
    assert mp.primary == "gpt-4o"
    assert mp.fallbacks == ["claude-3-5-sonnet", "qwen-2.5"]
    assert mp.required_capabilities == ["reasoning>=advanced"]
    assert "capacités" in mp.rationale.lower()  # justified by capabilities, not a provider
    assert mp.portability_note  # states any matching family can run the contract


def test_assumptions_come_from_evidence_and_noncritical_gaps() -> None:
    ev = _evidence(
        [
            EvidenceItem(
                statement="L'entreprise a 50 employés",
                evidence_class="assumption",
                source="user_provided",
                confidence="low",
            )
        ]
    )
    c = _build(
        _catr(missing_information=[MissingInformation(label="Budget cible", importance="low")]),
        evidence=ev,
    )
    assert any("50 employés" in a for a in c.assumptions)
    assert any("Budget cible" in a for a in c.assumptions)


def test_prompt_line_helpers_format_scope_and_success() -> None:
    c = _build(_catr(sub_goals=["Étape A"], constraints=["Max 200 mots"]))
    scope_lines = scope_prompt_lines(c)
    assert scope_lines[0] == "Dans le périmètre :"
    assert any("Hors périmètre :" == line for line in scope_lines)
    success_lines = success_prompt_lines(c)
    assert success_lines  # at least the base criterion
    assert all(line.startswith("- ") or line.endswith(":") for line in success_lines)


def test_note_holds_the_honesty_line() -> None:
    c = _build(_catr())
    assert "ne garantit pas" in c.note  # structures the work, does not promise completeness

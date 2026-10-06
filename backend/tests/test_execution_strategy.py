"""Unit tests for the Execution Strategy Engine (deterministic; no DB, no LLM).

Decomposition is derived from the stated sub-goals (linear deps for a chain, independent
otherwise) and never invented; tactics (decompose / tool-augmented / verification-loop /
ensemble) fire only on their signals; a simple low-risk task stays a direct pass; the woven
"recommended approach" lines appear only for non-trivial work.
"""

from __future__ import annotations

from app.engines.execution_strategy import ExecutionStrategyEngine, approach_prompt_lines
from app.schemas.catr import CanonicalAITask, CatrMeta
from app.schemas.strategize import ComplexityAssessment, Strategy


def _catr(**kw: object) -> CanonicalAITask:
    base: dict[str, object] = dict(
        objective="Rédige une note de synthèse",
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


def _complexity(level: str = "moderate") -> ComplexityAssessment:
    return ComplexityAssessment(level=level, score=0.5, features={}, method="rules-v1")  # type: ignore[arg-type]


def _strategy(kind: str = "single") -> Strategy:
    return Strategy(kind=kind, rationale="t", signals=[])  # type: ignore[arg-type]


def _plan(catr: CanonicalAITask, *, complexity="moderate", strategy="single", qc=None):
    return ExecutionStrategyEngine().plan(
        catr=catr,
        complexity=_complexity(complexity),
        strategy=_strategy(strategy),
        quality_contract=qc or [],
    )


def _reco(es) -> set[str]:
    return {t.tactic for t in es.tactics if t.recommended}


def test_simple_low_risk_task_is_a_direct_pass() -> None:
    es = _plan(_catr(domain="general", risk="low"), complexity="simple")
    assert es.primary == "direct"
    assert _reco(es) == set()
    assert es.decomposition == []
    assert approach_prompt_lines(es) == []  # nothing to add to the prompt


def test_decomposition_from_subgoals_linear_for_chain() -> None:
    catr = _catr(sub_goals=["Analyser", "Concevoir", "Rédiger"])
    chain = _plan(catr, complexity="complex", strategy="chain")
    assert [s.id for s in chain.decomposition] == [1, 2, 3]
    assert chain.decomposition[0].depends_on == []
    assert chain.decomposition[1].depends_on == [1]  # linear dependency in a chain
    assert "decomposition" in _reco(chain)
    # Independent decomposition when not a chain.
    indep = _plan(catr, complexity="complex", strategy="single")
    assert all(s.depends_on == [] for s in indep.decomposition)


def test_tool_augmented_from_inputs_or_rag_or_tool_words() -> None:
    assert "tool_augmented" in _reco(_plan(_catr(inputs=["data.csv"]), strategy="rag"))
    assert "tool_augmented" in _reco(
        _plan(_catr(objective="Récupère via l'API et calcule le total"))
    )
    assert "tool_augmented" not in _reco(_plan(_catr(objective="Explique la photosynthèse")))


def test_verification_loop_from_risk_software_or_quality_contract() -> None:
    assert "verification_loop" in _reco(_plan(_catr(risk="high")))
    assert "verification_loop" in _reco(_plan(_catr(domain="software")))
    assert "verification_loop" in _reco(_plan(_catr(), qc=["Couverture > 90%"]))
    assert "verification_loop" not in _reco(_plan(_catr(domain="general", risk="low")))


def test_ensemble_only_for_high_stakes() -> None:
    hi = _plan(
        _catr(objective="Choisir la meilleure architecture", risk="high"), complexity="complex"
    )
    assert "ensemble" in _reco(hi)
    # A medium-risk decision does not justify the cost of an ensemble.
    med = _plan(
        _catr(objective="Choisir la meilleure architecture", risk="medium"), complexity="complex"
    )
    assert "ensemble" not in _reco(med)


def test_primary_follows_priority_and_approach_lines_match() -> None:
    catr = _catr(
        sub_goals=["A", "B", "C"], domain="software", risk="high", objective="Choisir et bâtir"
    )
    es = _plan(catr, complexity="agentic", strategy="chain")
    # decomposition has top priority when it fires, even alongside others.
    assert es.primary == "decomposition"
    assert {"decomposition", "verification_loop", "ensemble"} <= _reco(es)
    lines = approach_prompt_lines(es)
    assert lines and lines[0].startswith("Décompose")  # decomposition directive leads
    assert any("vérifie" in line for line in lines)


def test_note_is_honest_about_the_executor_being_unchanged() -> None:
    es = _plan(_catr(domain="software"))
    assert "pas une garantie" in es.note
    assert "exécuteur n'est pas modifié" in es.note

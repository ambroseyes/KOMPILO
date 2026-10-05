"""Unit tests for the Evidence Engine (deterministic; no DB, no LLM).

Pins the honesty contract: the engine never promotes anything to a verified fact, user
material is classified as an operating assumption, known gaps become explicit unknowns,
and the emitted policy carries the labelling/citation rules plus the task's real unknowns.
"""

from __future__ import annotations

from app.engines.evidence import EvidenceEngine
from app.schemas.catr import CanonicalAITask, CatrMeta, MissingInformation
from app.schemas.strategize import Strategy


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


def test_engine_never_asserts_a_verified_fact() -> None:
    report = EvidenceEngine().assess(
        _catr(context=["Charte interne de l'entreprise"], inputs=["Journal des incidents"]),
        _strategy(),
    )
    # The conservative core of the layer: nothing is promoted to a fact on the engine's own.
    classes = {i.evidence_class for i in report.items}
    assert "fact" not in classes
    assert "verified_external_fact" not in classes


def test_user_material_is_an_assumption_from_user_provided_source() -> None:
    report = EvidenceEngine().assess(
        _catr(context=["Charte interne"], inputs=["Export CSV des accès"]), _strategy()
    )
    provided = [i for i in report.items if i.source == "user_provided"]
    assert len(provided) == 2  # one per context + input item
    assert all(i.evidence_class == "assumption" for i in provided)


def test_model_knowledge_is_an_inference_to_label() -> None:
    report = EvidenceEngine().assess(_catr(), _strategy())
    mk = [i for i in report.items if i.source == "model_knowledge"]
    assert len(mk) == 1
    assert mk[0].evidence_class == "inference"


def test_gaps_become_unknowns_and_are_named_in_the_policy() -> None:
    report = EvidenceEngine().assess(
        _catr(
            missing_information=[MissingInformation(label="Taille de la PME", importance="high")],
            ambiguities=["« sécurisé » n'est pas défini"],
        ),
        _strategy(),
    )
    unknowns = [i for i in report.items if i.evidence_class == "unknown"]
    assert len(unknowns) == 2
    assert all(i.source == "gap" for i in unknowns)
    assert "Taille de la PME" in report.unknowns
    # The unknowns are surfaced INTO the prompt policy so the model knows what not to invent.
    assert any("ne pas inventer" in line.lower() for line in report.policy)
    assert any("Taille de la PME" in line for line in report.policy)


def test_policy_carries_the_four_labelling_and_citation_rules() -> None:
    report = EvidenceEngine().assess(_catr(), _strategy())
    blob = " ".join(report.policy).lower()
    assert "fait" in blob and "inférence" in blob and "hypothèse" in blob and "inconnu" in blob
    assert "cite" in blob  # citation discipline
    assert len(report.hierarchy) == 4  # the canonical source-of-truth order, highest first
    assert report.injected is True


def test_rag_strategy_points_the_policy_at_retrieved_sources() -> None:
    report = EvidenceEngine().assess(_catr(context=["un document de référence"]), _strategy("rag"))
    assert any("récupérées" in line.lower() for line in report.policy)

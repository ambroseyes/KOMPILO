"""No-DB unit tests for the deterministic `understand` analyzer (heuristic-v1)."""

from __future__ import annotations

import pytest

from app.engines.understand import analyze_intent


def test_method_marker_is_heuristic() -> None:
    catr = analyze_intent("n'importe quoi")
    assert catr.method == "heuristic-v1"  # never presented as LLM output


def test_is_deterministic() -> None:
    intent = "Analyse les données du fichier ventes.csv et calcule la moyenne"
    assert analyze_intent(intent).model_dump() == analyze_intent(intent).model_dump()


@pytest.mark.parametrize(
    ("intent", "expected_type", "expected_lang"),
    [
        ("Implémente une fonction qui parse un fichier", "code_generation", "fr"),
        ("Analyse les données du fichier ventes.csv et calcule la moyenne", "data_analysis", "fr"),
        ("Write a short blog post about climate change", "writing", "en"),
        ("Pourquoi le ciel est-il bleu ?", "qa", "fr"),
        ("Planifie la roadmap du projet sur trois mois", "planning", "fr"),
        ("fais un truc", "other", "fr"),
    ],
)
def test_classification_and_language(intent: str, expected_type: str, expected_lang: str) -> None:
    catr = analyze_intent(intent)
    assert catr.task_type == expected_type
    assert catr.language == expected_lang
    assert 0.0 <= catr.confidence <= 1.0
    assert catr.goal  # always a non-empty normalized goal


def test_extracts_inputs_and_tech_entities() -> None:
    catr = analyze_intent("Analyse le fichier ventes.csv en Python")
    assert "ventes.csv" in catr.inputs
    assert any(e.lower() == "python" for e in catr.entities)


def test_language_constraint_detected() -> None:
    catr = analyze_intent("Rédige un article, réponds en français uniquement")
    assert any("français" in c.lower() for c in catr.constraints)


def test_open_questions_for_vague_intent() -> None:
    # Very short + unclassifiable → the analyzer surfaces clarifying questions.
    catr = analyze_intent("truc")
    assert catr.open_questions
    assert catr.confidence < 0.5


def test_code_without_language_asks_for_target() -> None:
    catr = analyze_intent("Corrige le bug dans la fonction de login")
    assert catr.task_type == "code_generation"
    assert any("langage" in q.lower() or "language" in q.lower() for q in catr.open_questions)

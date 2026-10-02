"""No-DB unit tests for the deterministic `understand` analyzer (heuristic-v1)."""
"""Unit tests for the understand contract and the fake LLM client.

No network, no API key, no database — these lock the shape that downstream
stages depend on and the behaviour of the test double.
"""

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
from pydantic import ValidationError

from app.engines.llm import FakeLLMClient
from app.engines.llm.base import LLMBadOutput, LLMToolCall
from app.schemas.understand import (
    AmbiguitySeverity,
    TaskType,
    UnderstandCore,
    UnderstandResult,
)


def _minimal_core() -> dict[str, object]:
    return {
        "normalized_intent": "Resume the article in three bullet points.",
        "language": "en",
        "goal": "Produce a 3-bullet summary.",
        "confidence": 0.9,
    }


# ── Contract: UnderstandCore / UnderstandResult ──────────────────────────────


def test_defaults_are_empty_lists_not_null() -> None:
    core = UnderstandCore(**_minimal_core())
    assert core.entities == []
    assert core.constraints == []
    assert core.deliverables == []
    assert core.success_criteria == []
    assert core.assumptions == []
    assert core.ambiguities == []
    assert core.task_type is TaskType.OTHER


def test_result_adds_derived_and_provenance_defaults() -> None:
    result = UnderstandResult(**_minimal_core())
    assert result.needs_clarification is False
    assert result.model is None
    assert result.usage == {}


@pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0, -1.0])
def test_confidence_must_be_within_unit_interval(bad: float) -> None:
    with pytest.raises(ValidationError):
        UnderstandCore(**{**_minimal_core(), "confidence": bad})


def test_task_type_rejects_unknown_label() -> None:
    with pytest.raises(ValidationError):
        UnderstandCore(**{**_minimal_core(), "task_type": "banana"})


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        UnderstandCore(**{**_minimal_core(), "surprise": "nope"})


def test_normalized_intent_cannot_be_empty() -> None:
    with pytest.raises(ValidationError):
        UnderstandCore(**{**_minimal_core(), "normalized_intent": ""})


def test_nested_models_parse() -> None:
    core = UnderstandCore(
        **{
            **_minimal_core(),
            "task_type": "qa",
            "entities": [{"name": "article", "type": "document"}],
            "ambiguities": [{"question": "Which article?", "severity": "high"}],
        }
    )
    assert core.task_type is TaskType.QA
    assert core.entities[0].name == "article"
    assert core.entities[0].value is None
    assert core.ambiguities[0].severity is AmbiguitySeverity.HIGH


def test_core_json_schema_is_tool_ready() -> None:
    schema = UnderstandCore.model_json_schema()
    required = set(schema["required"])
    # Fields without a default must be required of the model.
    assert {"normalized_intent", "language", "goal", "confidence"} <= required
    # Fields with defaults must NOT be required.
    assert "task_type" not in required
    assert "entities" not in required
    # The closed taxonomy is expressed as an enum in the schema.
    defs = schema.get("$defs", {})
    assert "TaskType" in defs
    assert set(defs["TaskType"]["enum"]) == {t.value for t in TaskType}


def test_result_schema_superset_of_core() -> None:
    assert set(UnderstandCore.model_fields) <= set(UnderstandResult.model_fields)
    assert {"needs_clarification", "model", "usage"} <= set(UnderstandResult.model_fields)


# ── FakeLLMClient ────────────────────────────────────────────────────────────


async def _emit(client: FakeLLMClient) -> LLMToolCall:
    return await client.emit_tool(
        system="sys",
        user="hello",
        tool_name="emit_understanding",
        tool_description="desc",
        input_schema={},
        model="fake-model",
        max_tokens=1024,
        temperature=0.0,
    )


async def test_fake_returns_queued_response_and_records_call() -> None:
    call = LLMToolCall(name="emit_understanding", arguments={"ok": True}, model="fake-model")
    client = FakeLLMClient([call])
    out = await _emit(client)
    assert out is call
    assert client.call_count == 1
    assert client.calls[0].user == "hello"
    assert client.calls[0].tool_name == "emit_understanding"


async def test_fake_raises_queued_exception() -> None:
    client = FakeLLMClient([LLMBadOutput("boom")])
    with pytest.raises(LLMBadOutput):
        await _emit(client)
    assert client.call_count == 1


async def test_fake_without_response_raises_bad_output() -> None:
    client = FakeLLMClient()
    with pytest.raises(LLMBadOutput):
        await _emit(client)


async def test_fake_queue_appends_in_order() -> None:
    first = LLMToolCall(name="t", arguments={"n": 1}, model="m")
    second = LLMToolCall(name="t", arguments={"n": 2}, model="m")
    client = FakeLLMClient()
    client.queue(first)
    client.queue(second)
    assert (await _emit(client)).arguments["n"] == 1
    assert (await _emit(client)).arguments["n"] == 2

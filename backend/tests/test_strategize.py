"""No-DB unit tests for the deterministic `strategize` planner (heuristic-v1)."""

from __future__ import annotations

import pytest

from app.engines.strategize import strategize_plan
from app.schemas.catr import Catr, TaskType


def _catr(**overrides: object) -> Catr:
    base: dict[str, object] = {
        "method": "heuristic-v1",
        "goal": "Faire la chose",
        "task_type": "code_generation",
        "language": "fr",
        "entities": [],
        "inputs": [],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
        "success_criteria": [],
        "confidence": 0.8,
    }
    base.update(overrides)
    return Catr.model_validate(base)


def test_method_marker_is_heuristic() -> None:
    strategy = strategize_plan(_catr())
    assert strategy.method == "heuristic-v1"  # never presented as LLM output


def test_is_deterministic() -> None:
    catr = _catr(task_type="data_analysis")
    assert strategize_plan(catr).model_dump() == strategize_plan(catr).model_dump()


@pytest.mark.parametrize(
    ("task_type", "expected_approach", "min_steps"),
    [
        ("code_generation", "multi_step", 3),
        ("data_analysis", "multi_step", 3),
        ("writing", "multi_step", 3),
        ("planning", "multi_step", 3),
        ("qa", "single_step", 1),
        ("other", "single_step", 1),
    ],
)
def test_approach_and_steps_by_task_type(
    task_type: TaskType, expected_approach: str, min_steps: int
) -> None:
    strategy = strategize_plan(_catr(task_type=task_type, confidence=0.8))
    assert strategy.approach == expected_approach
    assert strategy.needs_clarification is False
    assert len(strategy.steps) >= min_steps
    assert [s.order for s in strategy.steps] == list(range(1, len(strategy.steps) + 1))
    assert 0.0 <= strategy.confidence <= 1.0


def test_multi_step_dependencies_are_chained() -> None:
    strategy = strategize_plan(_catr(task_type="code_generation", confidence=0.9))
    assert strategy.steps[0].depends_on == []
    for i, step in enumerate(strategy.steps[1:], start=1):
        assert step.depends_on == [i]  # each step depends on the previous one


def test_open_questions_force_clarify_first() -> None:
    catr = _catr(
        task_type="code_generation",
        confidence=0.9,  # high confidence, but an unresolved question remains
        open_questions=["Quel langage cible ?"],
    )
    strategy = strategize_plan(catr)
    assert strategy.approach == "clarify_first"
    assert strategy.needs_clarification is True
    assert len(strategy.steps) == 1
    assert "Quel langage cible ?" in strategy.steps[0].description


def test_low_confidence_forces_clarify_first() -> None:
    strategy = strategize_plan(_catr(task_type="writing", confidence=0.3))
    assert strategy.approach == "clarify_first"
    assert strategy.needs_clarification is True


def test_plan_language_follows_catr_language() -> None:
    fr = strategize_plan(_catr(task_type="writing", language="fr", confidence=0.8))
    en = strategize_plan(_catr(task_type="writing", language="en", confidence=0.8))
    assert fr.steps[0].title == "Établir le plan"
    assert en.steps[0].title == "Outline"

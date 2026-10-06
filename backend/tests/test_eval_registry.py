"""Tests for the Compile Eval Registry (bloc G; deterministic, no DB, no LLM).

The default registry is the engine's regression baseline: replayed across the model sweep it
must stay fully green, so any regression in a block (B..F) trips a check. The runner also
proves it actually CATCHES a regression, only checks the expectations a fixture states, runs a
model-pinned case against that model alone, and reports per-model (cross-family) summaries.
"""

from __future__ import annotations

import pytest

from app.engines.eval_registry import DEFAULT_REGISTRY, CompileEvalRunner
from app.schemas.eval_registry import CompileEvalCase, CompileExpectation

_SWEEP = ["gpt-4o", "claude-sonnet-5-5"]


@pytest.mark.asyncio
async def test_default_registry_is_fully_green() -> None:
    # The regression guard: the designed guarantees (decision, sections, injection flagging,
    # evidence, family) hold for every fixture across the whole model sweep.
    report = await CompileEvalRunner().run()
    assert report.deterministic is True  # no LLM called → meaningful
    assert report.regressions == []
    assert report.pass_rate == 1.0
    assert report.n_cases == len(DEFAULT_REGISTRY)
    # Every case produced at least one check (no vacuously-empty fixture).
    assert all(r.checks for r in report.results)


@pytest.mark.asyncio
async def test_cross_model_sweep_runs_each_model_and_summarises_family() -> None:
    report = await CompileEvalRunner().run(target_models=_SWEEP)
    # A model-independent case yields one result per swept model.
    indep = [r for r in report.results if r.case == "trust_boundary_always_present"]
    assert {r.target_model for r in indep} == set(_SWEEP)
    # Per-model summaries expose the detected family (cross-family comparison).
    by = {s.target_model: s for s in report.by_model}
    assert by["claude-sonnet-5-5"].family == "anthropic"
    assert by["gpt-4o"].family == "openai"
    assert all(s.pass_rate == 1.0 for s in report.by_model)


@pytest.mark.asyncio
async def test_runner_catches_a_regression() -> None:
    # A fixture that expects the WRONG thing (ASK on a clearly actionable task) must be
    # reported as a regression — otherwise the guard would be worthless.
    bad = CompileEvalCase(
        name="should_proceed_but_expects_ask",
        task="Implémente une fonction Python qui additionne deux entiers, avec un test",
        expect=CompileExpectation(decision="ASK"),
    )
    report = await CompileEvalRunner().run(cases=[bad], target_models=["gpt-4o"])
    assert report.pass_rate == 0.0
    assert len(report.regressions) == 1
    failed = [c for c in report.regressions[0].checks if not c.passed]
    assert any(c.name == "decision" for c in failed)


@pytest.mark.asyncio
async def test_pinned_case_runs_only_against_its_model() -> None:
    case = CompileEvalCase(
        name="pin",
        task="Rédige une note de synthèse",
        target_model="claude-sonnet-5-5",
        expect=CompileExpectation(model_family="anthropic"),
    )
    report = await CompileEvalRunner().run(cases=[case], target_models=_SWEEP)
    # Pinned → one result on its own model, ignoring the sweep.
    assert len(report.results) == 1
    assert report.results[0].target_model == "claude-sonnet-5-5"
    assert report.results[0].passed is True


@pytest.mark.asyncio
async def test_only_stated_expectations_are_checked() -> None:
    # An expectation with a single field produces exactly one check.
    case = CompileEvalCase(
        name="one_check",
        task="truc",
        expect=CompileExpectation(decision="ASK"),
    )
    report = await CompileEvalRunner().run(cases=[case], target_models=["gpt-4o"])
    assert [c.name for c in report.results[0].checks] == ["decision"]


@pytest.mark.asyncio
async def test_note_is_honest_about_what_is_measured() -> None:
    report = await CompileEvalRunner().run(cases=[DEFAULT_REGISTRY[1]], target_models=["gpt-4o"])
    assert "PROCESSUS" in report.note
    assert "exactitude" in report.note  # it does NOT measure answer correctness
    assert report.method == "compile-eval-v1"

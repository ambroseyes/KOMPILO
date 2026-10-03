"""No-DB unit tests for the eval harness + version comparator (V1.5 #1).

Deterministic and offline: Kompilo Core compiles without a key, and the Executor/Gateway
is replaced by a fake whose output is the version's own prompt (so a richer instruction
scores higher). No network, no database.
"""

from __future__ import annotations

import uuid

import pytest

from app.engines.eval_harness import EvalHarness
from app.engines.executor import ExecutionOutcome, StepOutcome
from app.engines.version_comparator import ComparatorError, VersionComparator, VersionUnderTest
from app.schemas.benchmark import EvalCase


class _PromptEchoExecutor:
    """Returns the version's instruction (the part before the appended case input) as the
    output, with a controllable ``provider_is_real``. A version whose instruction reflects
    the case objective therefore measures higher — a deterministic, inspectable proxy."""

    def __init__(self, *, provider_is_real: bool = True) -> None:
        self._real = provider_is_real

    async def run(
        self, *, plan: object, compiled_prompt: str, tenant_id: str, json_mode: bool = False
    ) -> ExecutionOutcome:
        output = compiled_prompt.split("\n\n<input>")[0].strip()
        step = StepOutcome(
            order=1,
            action="generate",
            input_prompt=compiled_prompt,
            output=output,
            input_tokens=10,
            output_tokens=10,
            cost_usd=0.0,
            model="fake",
            cached=False,
            latency_ms=1,
        )
        return ExecutionOutcome(
            output=output,
            steps=[step],
            provider="fake",
            provider_is_real=self._real,
        )


def _harness(*, provider_is_real: bool = True) -> EvalHarness:
    return EvalHarness(executor=_PromptEchoExecutor(provider_is_real=provider_is_real))  # type: ignore[arg-type]


_CASE = EvalCase(name="c1", task="Explique la photosynthèse avec des exemples concrets")
_WEAK = "Sois bref."
_STRONG = "Explique la photosynthèse avec des exemples concrets et détaillés, étape par étape."


async def test_harness_measures_and_propagates_provider_flag() -> None:
    harness = _harness(provider_is_real=False)
    catr, plan = await harness.prepare_case(_CASE)
    score = await harness.measure(
        compiled_prompt=_STRONG, case=_CASE, case_catr=catr, plan=plan, tenant_id="t1"
    )
    assert 0.0 <= score.score <= 1.0
    assert score.provider_is_real is False  # propagated from the (stub) executor
    assert score.criteria  # measured, with evidence


async def test_comparison_ranks_the_stronger_version_higher() -> None:
    comparator = VersionComparator(harness=_harness())
    result = await comparator.compare(
        prompt_id=uuid.uuid4(),
        a=VersionUnderTest(version=1, prompt_text=_WEAK, source_intent="x"),
        b=VersionUnderTest(version=2, prompt_text=_STRONG, source_intent="x"),
        cases=[_CASE],
        tenant_id="t1",
    )
    assert result.verdict == "to_better"
    assert result.margin > 0
    assert result.to_result.mean_score > result.from_result.mean_score
    assert result.provider_is_real is True


async def test_comparison_flags_stub_outputs_as_not_meaningful() -> None:
    comparator = VersionComparator(harness=_harness(provider_is_real=False))
    result = await comparator.compare(
        prompt_id=uuid.uuid4(),
        a=VersionUnderTest(version=1, prompt_text=_STRONG, source_intent="x"),
        b=VersionUnderTest(version=2, prompt_text=_STRONG, source_intent="x"),
        cases=[_CASE],
        tenant_id="t1",
    )
    assert result.provider_is_real is False
    assert "STUB" in result.note  # honest: ranking over stub outputs is flagged
    assert result.verdict == "tie"  # identical prompts → tie within the margin


async def test_identical_versions_detect_no_regression() -> None:
    comparator = VersionComparator(harness=_harness())
    result = await comparator.compare(
        prompt_id=uuid.uuid4(),
        a=VersionUnderTest(version=1, prompt_text=_STRONG, source_intent="x"),
        b=VersionUnderTest(version=2, prompt_text=_STRONG, source_intent="x"),
        cases=[_CASE],
        tenant_id="t1",
    )
    assert result.regressions == []
    assert result.verdict == "tie"


async def test_regression_surfaced_when_newer_version_is_worse() -> None:
    comparator = VersionComparator(harness=_harness())
    result = await comparator.compare(
        prompt_id=uuid.uuid4(),
        a=VersionUnderTest(version=1, prompt_text=_STRONG, source_intent="x"),
        b=VersionUnderTest(version=2, prompt_text=_WEAK, source_intent="x"),
        cases=[_CASE],
        tenant_id="t1",
    )
    assert result.verdict == "from_better"
    assert result.regressions and result.regressions[0].delta < 0


async def test_no_cases_derives_a_baseline_from_source_intent() -> None:
    comparator = VersionComparator(harness=_harness())
    result = await comparator.compare(
        prompt_id=uuid.uuid4(),
        a=VersionUnderTest(version=1, prompt_text=_STRONG, source_intent="Explique un concept"),
        b=VersionUnderTest(version=2, prompt_text=_STRONG, source_intent="Explique un concept"),
        cases=[],
        tenant_id="t1",
    )
    assert result.from_result.cases and result.from_result.cases[0].case == "baseline"


async def test_no_cases_and_no_source_intent_is_refused() -> None:
    comparator = VersionComparator(harness=_harness())
    with pytest.raises(ComparatorError):
        await comparator.compare(
            prompt_id=uuid.uuid4(),
            a=VersionUnderTest(version=1, prompt_text=_STRONG, source_intent=None),
            b=VersionUnderTest(version=2, prompt_text=_STRONG, source_intent=None),
            cases=[],
            tenant_id="t1",
        )

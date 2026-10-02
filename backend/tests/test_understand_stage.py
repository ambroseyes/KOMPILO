"""Unit tests for the real UnderstandStage (no network, scripted FakeLLMClient)."""

from __future__ import annotations

import pytest

from app.engines.base import PipelineContext
from app.engines.llm import FakeLLMClient
from app.engines.llm.base import LLMBadOutput, LLMTimeout, LLMToolCall
from app.engines.stages import UnderstandStage


def _valid_args(**overrides: object) -> dict[str, object]:
    args: dict[str, object] = {
        "normalized_intent": "Summarise the article in three bullets.",
        "language": "en",
        "task_type": "qa",
        "goal": "Produce a 3-bullet summary.",
        "confidence": 0.9,
    }
    args.update(overrides)
    return args


def _call(args: dict[str, object]) -> LLMToolCall:
    return LLMToolCall(
        name="emit_understanding",
        arguments=args,
        model="fake-model",
        usage={"input_tokens": 10, "output_tokens": 20},
    )


def _ctx(intent: str = "Summarise this article", **context: object) -> PipelineContext:
    return PipelineContext(intent=intent, context=dict(context))


async def test_nominal_produces_validated_understanding() -> None:
    llm = FakeLLMClient([_call(_valid_args())])
    ctx = _ctx()
    result = await UnderstandStage(llm).run(ctx)

    assert result.status == "ok"
    assert ctx.artifacts["understand"]["task_type"] == "qa"
    assert ctx.artifacts["understand"]["needs_clarification"] is False
    assert ctx.artifacts["understand"]["model"] == "fake-model"
    assert ctx.artifacts["understand"]["usage"] == {"input_tokens": 10, "output_tokens": 20}
    assert llm.call_count == 1
    # The intent is passed as delimited data, not bare.
    assert "<intent>" in llm.calls[0].user


async def test_empty_intent_errors_without_calling_llm() -> None:
    llm = FakeLLMClient([_call(_valid_args())])
    result = await UnderstandStage(llm).run(_ctx(intent="   "))
    assert result.status == "error"
    assert llm.call_count == 0


async def test_no_client_errors() -> None:
    result = await UnderstandStage(None).run(_ctx())
    assert result.status == "error"
    assert "understand" not in _ctx().artifacts


async def test_high_severity_ambiguity_sets_needs_clarification() -> None:
    args = _valid_args(
        ambiguities=[{"question": "Which article?", "severity": "high"}],
    )
    llm = FakeLLMClient([_call(args)])
    ctx = _ctx()
    result = await UnderstandStage(llm).run(ctx)
    assert result.status == "ok"
    assert ctx.artifacts["understand"]["needs_clarification"] is True


async def test_low_confidence_sets_needs_clarification() -> None:
    llm = FakeLLMClient([_call(_valid_args(confidence=0.2))])
    ctx = _ctx()
    result = await UnderstandStage(llm).run(ctx)
    assert result.status == "ok"
    assert ctx.artifacts["understand"]["needs_clarification"] is True


async def test_transient_error_then_success_retries() -> None:
    llm = FakeLLMClient([LLMTimeout("slow"), _call(_valid_args())])
    ctx = _ctx()
    result = await UnderstandStage(llm).run(ctx)
    assert result.status == "ok"
    assert llm.call_count == 2


async def test_malformed_output_then_success_retries() -> None:
    # Missing required 'confidence' -> ValidationError -> retry.
    bad = _valid_args()
    del bad["confidence"]
    llm = FakeLLMClient([_call(bad), _call(_valid_args())])
    ctx = _ctx()
    result = await UnderstandStage(llm).run(ctx)
    assert result.status == "ok"
    assert llm.call_count == 2


async def test_persistent_failure_errors_after_bounded_retries() -> None:
    # Default llm_max_retries = 2 -> 3 attempts.
    llm = FakeLLMClient([LLMBadOutput("no tool"), LLMBadOutput("no tool"), LLMBadOutput("no tool")])
    ctx = _ctx()
    result = await UnderstandStage(llm).run(ctx)
    assert result.status == "error"
    assert llm.call_count == 3
    assert "understand" not in ctx.artifacts


async def test_invented_task_type_is_rejected_and_retried() -> None:
    llm = FakeLLMClient([_call(_valid_args(task_type="banana")), _call(_valid_args())])
    ctx = _ctx()
    result = await UnderstandStage(llm).run(ctx)
    assert result.status == "ok"
    assert llm.call_count == 2


@pytest.mark.parametrize("locale,expected", [("fr-FR", True), ("", False)])
async def test_locale_hint_included_when_present(locale: str, expected: bool) -> None:
    llm = FakeLLMClient([_call(_valid_args())])
    ctx = _ctx(locale=locale)
    await UnderstandStage(llm).run(ctx)
    assert ("Requested response language" in llm.calls[0].user) is expected

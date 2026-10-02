"""Unit tests for the Prompt Compiler (deterministic, no DB, no LLM).

Checks dynamic section selection (no decorative empty sections), the three renders, the
expert rigor/JSON tuning from the model profile, and mode selection.
"""

from __future__ import annotations

from datetime import date

from app.engines.prompt_compiler import PromptCompiler
from app.schemas.catr import CanonicalAITask, CatrMeta
from app.schemas.registry import ModelCapability


def _catr(**overrides: object) -> CanonicalAITask:
    base: dict[str, object] = {
        "objective": "Résumer un rapport financier trimestriel",
        "domain": "writing",
        "complexity": "medium",
        "risk": "low",
        "meta": CatrMeta(method="heuristic-v1", confidence=0.8, enriched_by_llm=False),
    }
    base.update(overrides)
    return CanonicalAITask(**base)  # type: ignore[arg-type]


def _profile(*, reasoning: str = "advanced", structured: bool = True) -> ModelCapability:
    return ModelCapability(
        model="m",
        provider="p",
        context_window=8000,
        supports_tools=True,
        supports_vision=False,
        structured_output=structured,
        reasoning_strength=reasoning,  # type: ignore[arg-type]
        cost_in=1.0,
        cost_out=2.0,
        latency_ms=100,
        last_verified=date(2026, 1, 1),
    )


def test_role_and_mission_always_present_others_dynamic() -> None:
    # A minimal CATR with no output spec → only role + mission (no decorative sections).
    renders, compiled = PromptCompiler().compile(
        _catr(), None, mode="professional", output_format="", quality_contract=[]
    )
    assert compiled.sections == ["role", "mission"]
    assert "## Role" in renders.professional and "## Mission" in renders.professional
    # None of the optional sections leak in when the CATR has no content for them.
    for absent in ("Context", "Steps", "Constraints", "Audience", "Output format"):
        assert f"## {absent}" not in renders.professional


def test_optional_sections_appear_with_content() -> None:
    _, compiled = PromptCompiler().compile(
        _catr(
            context=["Le rapport fait 20 pages"],
            sub_goals=["Lire", "Extraire les chiffres clés", "Rédiger la synthèse"],
            constraints=["Max 200 mots"],
            audience="Comité de direction",
            expected_output="Une synthèse en 5 points",
        ),
        None,
        mode="professional",
        output_format="markdown",
        quality_contract=["Ton neutre"],
    )
    assert {"context", "steps", "constraints", "audience", "output_format"} <= set(
        compiled.sections
    )


def test_expert_render_adds_rigor_and_json_rule() -> None:
    renders, _ = PromptCompiler().compile(
        _catr(),
        _profile(reasoning="frontier", structured=True),
        mode="expert",
        output_format="json",
        quality_contract=[],
    )
    assert "## Rigor" in renders.expert
    assert "step by step" in renders.expert.lower()
    assert "strictly valid json" in renders.expert.lower()  # structured_output + json mode


def test_mode_selects_matching_render() -> None:
    renders, compiled = PromptCompiler().compile(
        _catr(), None, mode="compact", output_format="markdown", quality_contract=[]
    )
    assert compiled.mode == "compact"
    assert compiled.text == renders.compact
    # Compact is terser than professional for the same IR.
    assert len(renders.compact) <= len(renders.professional)


def test_validation_section_from_risk() -> None:
    _, compiled = PromptCompiler().compile(
        _catr(risk="high"),
        None,
        mode="professional",
        output_format="markdown",
        quality_contract=[],
    )
    assert "validation" in compiled.sections  # high risk injects a validation section

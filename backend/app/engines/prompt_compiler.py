"""Prompt Compiler v1 — CATR + target-model profile → IR → render variants.

Deterministic. Builds an intermediate representation (an ordered list of sections) by
DYNAMICALLY selecting only the sections that have real content (no decorative sections:
``role`` and ``mission`` are always present; everything else appears only when the CATR
provides it). It then renders three variants from that one IR:

- ``compact``: a terse single block (role + mission + key constraints/output).
- ``professional``: clear markdown sections — the balanced default.
- ``expert``: professional + a rigor section, tuned to the target model's profile
  (step-by-step for strong reasoners, strict-JSON when the model supports structured
  output and JSON is requested).
"""

from __future__ import annotations

from app.schemas.catr import CanonicalAITask
from app.schemas.compile import CompiledPrompt, CompileMode, PromptRenders, PromptSection
from app.schemas.registry import ModelCapability

_ROLE_BY_DOMAIN: dict[str, str] = {
    "software": "You are an expert software engineer.",
    "data": "You are an expert data analyst.",
    "writing": "You are an expert writer and editor.",
    "product": "You are an expert product strategist.",
    "general": "You are a rigorous, helpful expert assistant.",
}

_SECTION_TITLE: dict[str, str] = {
    "role": "Role",
    "mission": "Mission",
    "context": "Context",
    "steps": "Steps",
    "constraints": "Constraints",
    "audience": "Audience",
    "output_format": "Output format",
    "validation": "Validation",
}


def _build_ir(
    catr: CanonicalAITask, *, output_format: str, quality_contract: list[str]
) -> list[PromptSection]:
    sections: list[PromptSection] = [
        PromptSection(
            name="role", content=_ROLE_BY_DOMAIN.get(catr.domain, _ROLE_BY_DOMAIN["general"])
        ),
        PromptSection(name="mission", content=catr.objective),
    ]

    context_items = [*catr.context, *catr.inputs]
    if context_items:
        sections.append(
            PromptSection(name="context", content="\n".join(f"- {c}" for c in context_items))
        )
    if catr.sub_goals:
        sections.append(
            PromptSection(
                name="steps",
                content="\n".join(f"{i}. {g}" for i, g in enumerate(catr.sub_goals, start=1)),
            )
        )
    if catr.constraints:
        sections.append(
            PromptSection(name="constraints", content="\n".join(f"- {c}" for c in catr.constraints))
        )
    if catr.audience:
        sections.append(PromptSection(name="audience", content=catr.audience))

    output_bits: list[str] = []
    if catr.expected_output:
        output_bits.append(catr.expected_output)
    if output_format:
        output_bits.append(f"Respond in {output_format}.")
    if output_bits:
        sections.append(PromptSection(name="output_format", content=" ".join(output_bits)))

    validation_bits = list(quality_contract)
    if catr.risk in {"medium", "high"}:
        validation_bits.append(
            f"{catr.risk.capitalize()} risk — double-check correctness and side effects."
        )
    if validation_bits:
        sections.append(
            PromptSection(name="validation", content="\n".join(f"- {v}" for v in validation_bits))
        )

    return sections


def _render_professional(sections: list[PromptSection]) -> str:
    return "\n\n".join(f"## {_SECTION_TITLE[s.name]}\n{s.content}" for s in sections)


def _render_compact(sections: list[PromptSection]) -> str:
    by_name = {s.name: s.content for s in sections}
    parts = [by_name["role"], by_name["mission"]]
    if "constraints" in by_name:
        inline = by_name["constraints"].replace("\n", " ").replace("- ", "")
        parts.append(f"Constraints: {inline}")
    if "output_format" in by_name:
        parts.append(by_name["output_format"])
    return " ".join(parts)


def _render_expert(
    sections: list[PromptSection], profile: ModelCapability | None, output_format: str
) -> str:
    body = _render_professional(sections)
    rigor: list[str] = []
    if profile is not None and profile.reasoning_rank >= 3:
        rigor.append("Reason step by step before answering; state assumptions explicitly.")
    else:
        rigor.append("Work carefully and state any assumptions you make.")
    if output_format.lower() == "json" and profile is not None and profile.structured_output:
        rigor.append("Return strictly valid JSON only — no prose outside the JSON object.")
    rigor.append("Before finishing, self-check the result against the Mission and Validation.")
    return body + "\n\n## Rigor\n" + "\n".join(f"- {r}" for r in rigor)


class PromptCompiler:
    """Compile a CATR into prompt render variants (deterministic)."""

    def compile(
        self,
        catr: CanonicalAITask,
        profile: ModelCapability | None,
        *,
        mode: CompileMode,
        output_format: str,
        quality_contract: list[str],
    ) -> tuple[PromptRenders, CompiledPrompt]:
        ir = _build_ir(catr, output_format=output_format, quality_contract=quality_contract)
        renders = PromptRenders(
            compact=_render_compact(ir),
            professional=_render_professional(ir),
            expert=_render_expert(ir, profile, output_format),
        )
        selected = getattr(renders, mode)
        compiled = CompiledPrompt(mode=mode, text=selected, sections=[s.name for s in ir], ir=ir)
        return renders, compiled

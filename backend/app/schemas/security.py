"""Security layer — prompt-injection detection + trust boundaries (Framework §20, CDC §16).

The prompt engine is itself a security boundary: content the user supplies, and content
retrieved from a corpus, must be treated as DATA to analyse, never as instructions to
obey. This module's report carries (a) deterministic findings from scanning the task for
direct-injection patterns and (b) the trust-boundary policy woven into the compiled prompt
so the model treats any delimited/retrieved block (e.g. the executor's ``<context>`` block)
as data.

Honesty stance (Ambro's principle): a rules-based detector catches KNOWN patterns — it is
defense-in-depth, not a guarantee; it can miss novel attacks and flag benign text. The
robust part is the trust-boundary FRAMING, always injected, independent of detection.

Kept decoupled from ``schemas.compile`` (no import from it) so ``CompileResponse`` can
embed a ``SecurityReport`` without a circular import.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["low", "medium", "high"]

# Machine keys for the kinds of injection / exposure the scanner recognises.
InjectionKind = Literal[
    "instruction_override",  # "ignore previous instructions", "disregard the above"
    "role_switch",  # "you are now…", "pretend to be…"
    "prompt_leak",  # "reveal your system prompt", "print your instructions"
    "exfiltration",  # "send the api key to…", "leak the secret"
    "jailbreak",  # "developer mode", "do anything now", "without any restrictions"
    "indirect_injection_surface",  # retrieved/external content will be injected (RAG)
]


class SecurityFinding(BaseModel):
    """One injection pattern matched in the task, or an exposure surface identified."""

    model_config = ConfigDict(extra="forbid")

    kind: InjectionKind
    severity: Severity
    label: str  # human label (French)
    detail: str  # what matched (quoted user data) or why the surface exists
    recommendation: str


class SecurityReport(BaseModel):
    """Injection findings + the trust-boundary policy woven into the compiled prompt."""

    model_config = ConfigDict(extra="forbid")

    risk: Severity  # highest finding severity; "low" when nothing suspicious was found
    findings: list[SecurityFinding] = Field(default_factory=list)
    boundary_policy: list[str] = Field(default_factory=list)  # directives woven in
    injected: bool = False  # whether the trust-boundary section is in the compiled prompt
    summary: str
    note: str

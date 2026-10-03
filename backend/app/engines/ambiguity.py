"""Ambiguity Engine v1 — decide ASK vs PROCEED from a CATR.

Deterministic, rule-based. Consumes a :class:`~app.schemas.catr.CanonicalAITask` and
surfaces three kinds of problem: vague terms, contradictory constraints, and missing
information — each classified CRITICAL / IMPORTANT / OPTIONAL.

Decision rule (strict): **ASK only if at least one CRITICAL is present**, and then with
the minimum number of targeted questions (1–3), one per unresolved CRITICAL. Otherwise
PROCEED. The engine NEVER invents the missing information — it only asks for it.
"""

from __future__ import annotations

import re

from app.schemas.catr import CanonicalAITask, Importance
from app.schemas.strategize import AmbiguityFinding, AmbiguityReport, Decision, Severity

_MAX_QUESTIONS = 3

# Clearly-vague qualifiers (fr/en). Matched as whole words, case-insensitive.
_VAGUE_TERMS: frozenset[str] = frozenset(
    "truc trucs chose choses machin ça ca bien vite rapidement propre simple optimal"
    " meilleur approprié pertinent correct bon it this that stuff thing things nice fast"
    " clean good best appropriate proper relevant some".split()
)
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

_SEVERITY_FOR_IMPORTANCE: dict[Importance, Severity] = {
    "high": "CRITICAL",
    "medium": "IMPORTANT",
    "low": "OPTIONAL",
}

_BRIEF_TERMS = ("court", "bref", "concis", "concise", "short", "brief")
_LONG_TERMS = ("détaillé", "detaille", "exhaustif", "exhaustive", "long", "detailed", "approfondi")


def _detect_vague_terms(catr: CanonicalAITask) -> list[str]:
    haystack = " ".join([catr.objective, *catr.constraints, *catr.sub_goals]).lower()
    tokens = _WORD_RE.findall(haystack)
    return sorted({tok for tok in tokens if tok in _VAGUE_TERMS})


def _detect_contradictions(catr: CanonicalAITask) -> list[str]:
    joined = " ".join([catr.objective, *catr.constraints]).lower()
    out: list[str] = []
    wants_fr = "français" in joined or "french" in joined
    wants_en = "anglais" in joined or "english" in joined
    if wants_fr and wants_en:
        out.append("langue de sortie demandée à la fois en français et en anglais")
    if any(t in joined for t in _BRIEF_TERMS) and any(t in joined for t in _LONG_TERMS):
        out.append("exigences de longueur contradictoires (concis vs exhaustif)")
    return out


def _question_for(finding: AmbiguityFinding) -> str:
    if finding.kind == "missing_information":
        return f"Information manquante : {finding.detail}. Peux-tu la préciser ?"
    if finding.kind == "contradiction":
        return f"Les contraintes se contredisent ({finding.detail}). Laquelle prévaut ?"
    return f"Peux-tu préciser « {finding.detail} » ?"


class AmbiguityEngine:
    """Rule-based ASK/PROCEED decision over a CATR."""

    def analyze(self, catr: CanonicalAITask) -> AmbiguityReport:
        findings: list[AmbiguityFinding] = []

        # 1. Missing information — taken from the CATR, never invented.
        for missing in catr.missing_information:
            findings.append(
                AmbiguityFinding(
                    kind="missing_information",
                    severity=_SEVERITY_FOR_IMPORTANCE[missing.importance],
                    detail=missing.label,
                )
            )

        # 2. Contradictions — mutually exclusive requirements block correct execution.
        for detail in _detect_contradictions(catr):
            findings.append(
                AmbiguityFinding(kind="contradiction", severity="CRITICAL", detail=detail)
            )

        # 3. Vague terms (surfaced, not blocking on their own).
        for term in _detect_vague_terms(catr):
            findings.append(AmbiguityFinding(kind="vague_term", severity="IMPORTANT", detail=term))
        for ambiguity in catr.ambiguities:  # already-noted ambiguities from the CATR
            findings.append(
                AmbiguityFinding(kind="vague_term", severity="IMPORTANT", detail=ambiguity)
            )

        # Decision: ASK only when a CRITICAL is present; minimum questions (1 per CRITICAL).
        criticals = [f for f in findings if f.severity == "CRITICAL"]
        decision: Decision = "ASK" if criticals else "PROCEED"
        questions: list[str] = []
        if criticals:
            seen: set[str] = set()
            for finding in criticals:
                q = _question_for(finding)
                if q not in seen:
                    seen.add(q)
                    questions.append(q)
                if len(questions) >= _MAX_QUESTIONS:
                    break

        return AmbiguityReport(decision=decision, questions=questions, findings=findings)

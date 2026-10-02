"""The `understand` stage — deterministic, offline, heuristic intent analysis.

HEURISTIC, NOT AI/LLM. This module turns a raw human intent into a
:class:`~app.schemas.catr.Catr` using rule-based text analysis only: keyword
classification, pattern extraction and small bilingual (fr/en) templates. It is
fully deterministic (same input → same output), needs no API key and no network,
and is therefore unit-testable in isolation.

The emitted CATR carries ``method="heuristic-v1"`` so no consumer mistakes it for
model reasoning. A Claude-backed analyzer can later replace this behind the exact
same ``analyze_intent(intent, context) -> Catr`` signature; everything downstream
(the stage wrapper, the worker task, the API) stays unchanged.
"""

from __future__ import annotations

import re
from typing import Any

from app.schemas.catr import Catr, TaskType

# ── Keyword tables (lowercase; matched on word boundaries, fr + en) ──────────────
# Order of TASK_KEYWORDS is also the tie-break priority when scores are equal.
TASK_KEYWORDS: dict[TaskType, tuple[str, ...]] = {
    "code_generation": (
        "code",
        "coder",
        "implémente",
        "implémenter",
        "fonction",
        "classe",
        "bug",
        "corrige",
        "refactor",
        "refactorise",
        "script",
        "api",
        "endpoint",
        "programme",
        "débogue",
        "debug",
        "implement",
        "function",
        "class",
        "refactoring",
        "module",
        "library",
        "librairie",
        "compile",
        "compiler",
    ),
    "data_analysis": (
        "analyse",
        "analyser",
        "données",
        "data",
        "dataset",
        "csv",
        "statistiques",
        "statistics",
        "graphique",
        "chart",
        "corrélation",
        "correlation",
        "agrège",
        "aggregate",
        "moyenne",
        "average",
        "insight",
        "kpi",
        "metrics",
        "métriques",
    ),
    "writing": (
        "rédige",
        "rédiger",
        "écris",
        "écrire",
        "article",
        "blog",
        "email",
        "courriel",
        "texte",
        "rédaction",
        "résume",
        "résumé",
        "summary",
        "write",
        "draft",
        "essay",
        "post",
        "lettre",
        "letter",
        "traduis",
        "translate",
        "traduire",
    ),
    "planning": (
        "plan",
        "planifie",
        "planifier",
        "étapes",
        "roadmap",
        "stratégie",
        "strategy",
        "organise",
        "organiser",
        "backlog",
        "jalons",
        "milestones",
        "priorise",
        "prioritize",
        "feuille de route",
    ),
    "qa": (
        "pourquoi",
        "comment",
        "qu'est-ce",
        "quelle",
        "quel",
        "explique",
        "explication",
        "what",
        "why",
        "how",
        "explain",
        "define",
        "définis",
        "différence",
        "difference",
    ),
}

# Canonical technology tokens recognised as entities.
TECH_TOKENS: tuple[str, ...] = (
    "python",
    "javascript",
    "typescript",
    "java",
    "golang",
    "rust",
    "fastapi",
    "django",
    "flask",
    "react",
    "vue",
    "angular",
    "postgres",
    "postgresql",
    "mysql",
    "sqlite",
    "redis",
    "docker",
    "kubernetes",
    "sql",
    "json",
    "csv",
    "yaml",
    "rest",
    "graphql",
    "aws",
    "gcp",
    "azure",
    "pandas",
    "numpy",
    "pytorch",
    "tensorflow",
)

_FR_ACCENTS = re.compile(r"[àâäéèêëîïôöùûüÿç]")
_FR_STOPWORDS = frozenset(
    "le la les un une des et avec pour dans que qui est sur en au aux du de ce cette"
    " ton ta tes mon ma mes nous vous ils elles être avoir faire".split()
)
_EN_STOPWORDS = frozenset(
    "the a an and with for in that which is on at of this these your my we you they"
    " be have do make to from".split()
)

_CONSTRAINT_KEYWORDS: tuple[str, ...] = (
    "doit",
    "devra",
    "must",
    "sans",
    "without",
    "uniquement",
    "only",
    "maximum",
    "max",
    "au plus",
    "at most",
    "moins de",
    "format",
    "en français",
    "in french",
    "en anglais",
    "in english",
    "ton ",
    "tone",
    "longueur",
    "length",
    "mots",
    "words",
    "caractères",
    "characters",
    "deadline",
    "avant",
    "before",
    "obligatoire",
    "required",
    "respecter",
)

_INPUT_KEYWORDS: tuple[str, ...] = (
    "ci-dessous",
    "ci-dessus",
    "attaché",
    "attached",
    "fourni",
    "provided",
    "ce fichier",
    "this file",
    "le texte suivant",
    "the following",
    "ce texte",
)

_FILE_RE = re.compile(r"\b[\w\-./]+\.(?:csv|json|txt|xlsx|pdf|md|parquet|sql|ya?ml)\b", re.I)
_URL_RE = re.compile(r"https?://\S+")
_QUOTED_RE = re.compile(r"[\"'«“]([^\"'»”]{1,80})[\"'»”]")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_SENTENCE_SPLIT_RE = re.compile(r"[.?!\n]+")
_CLAUSE_SPLIT_RE = re.compile(r"[,;.\n]+")

_MAX_LIST = 12
_GOAL_MAX = 200


def _t(language: str, fr: str, en: str) -> str:
    """Pick the French or English template for the detected language."""
    return fr if language == "fr" else en


def _language_name(language: str) -> str:
    return {"fr": "français", "en": "English"}.get(language, language)


def _dedupe(items: list[str]) -> list[str]:
    """De-duplicate while preserving first-seen order (case-insensitive key)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _detect_language(text: str, lower: str) -> str:
    if _FR_ACCENTS.search(text):
        return "fr"
    tokens = _WORD_RE.findall(lower)
    fr = sum(1 for tok in tokens if tok in _FR_STOPWORDS)
    en = sum(1 for tok in tokens if tok in _EN_STOPWORDS)
    if fr > en:
        return "fr"
    return "en"


def _classify_task_type(lower: str) -> TaskType:
    scores: dict[TaskType, int] = {}
    for task_type, keywords in TASK_KEYWORDS.items():
        scores[task_type] = sum(1 for kw in keywords if kw in lower)
    if "?" in lower:
        scores["qa"] = scores.get("qa", 0) + 1
    best = max(scores.values())
    if best == 0:
        return "other"
    # Tie-break by TASK_KEYWORDS insertion order (dict preserves it).
    for task_type in TASK_KEYWORDS:
        if scores[task_type] == best:
            return task_type
    return "other"


def _extract_entities(text: str, lower: str) -> list[str]:
    found: list[str] = []
    found += [m.group(1).strip() for m in _QUOTED_RE.finditer(text)]
    found += [tok for tok in TECH_TOKENS if re.search(rf"\b{re.escape(tok)}\b", lower)]
    # Title-case words that are not the first token of a sentence and not stopwords.
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        words = sentence.strip().split()
        for word in words[1:]:
            cleaned = word.strip(".,;:!?()[]\"'")
            if len(cleaned) > 1 and cleaned[0].isupper() and cleaned.lower() not in _FR_STOPWORDS:
                found.append(cleaned)
    return _dedupe(found)[:_MAX_LIST]


def _extract_inputs(text: str, lower: str, language: str) -> list[str]:
    found: list[str] = []
    found += _URL_RE.findall(text)
    found += [m.group(0) for m in _FILE_RE.finditer(text)]
    if any(kw in lower for kw in _INPUT_KEYWORDS):
        found.append(_t(language, "contenu fourni par l'utilisateur", "user-provided content"))
    return _dedupe(found)[:_MAX_LIST]


def _extract_constraints(text: str, lower: str, language: str) -> list[str]:
    found: list[str] = []
    for clause in _CLAUSE_SPLIT_RE.split(text):
        c = clause.strip()
        if c and any(kw in c.lower() for kw in _CONSTRAINT_KEYWORDS):
            found.append(c)
    if "en français" in lower or "in french" in lower:
        found.append(_t(language, "Langue de sortie : français", "Output language: French"))
    if "en anglais" in lower or "in english" in lower:
        found.append(_t(language, "Langue de sortie : anglais", "Output language: English"))
    return _dedupe(found)[:_MAX_LIST]


def _has_programming_signal(entities: list[str], lower: str) -> bool:
    langs = {"python", "javascript", "typescript", "java", "golang", "rust"}
    if any(e.lower() in langs for e in entities):
        return True
    return any(re.search(rf"\b{re.escape(t)}\b", lower) for t in langs)


def _derive_assumptions(
    task_type: TaskType, language: str, entities: list[str], lower: str
) -> list[str]:
    out = [
        _t(
            language,
            f"Réponse attendue en {_language_name(language)}.",
            f"Response expected in {_language_name(language)}.",
        )
    ]
    if task_type == "code_generation" and not _has_programming_signal(entities, lower):
        out.append(
            _t(
                language,
                "Aucun langage cible détecté ; le choix est laissé à l'étape de routage.",
                "No target language detected; the choice is left to the routing stage.",
            )
        )
    return _dedupe(out)[:_MAX_LIST]


def _derive_open_questions(
    task_type: TaskType,
    language: str,
    entities: list[str],
    inputs: list[str],
    constraints: list[str],
    word_count: int,
    lower: str,
) -> list[str]:
    out: list[str] = []
    if task_type == "code_generation" and not _has_programming_signal(entities, lower):
        out.append(
            _t(language, "Quel langage ou framework cible ?", "Which target language or framework?")
        )
    if task_type == "data_analysis" and not inputs:
        out.append(_t(language, "Quelle est la source des données ?", "What is the data source?"))
    if task_type == "writing" and not constraints:
        out.append(
            _t(
                language,
                "Quelle longueur et quel format attendus ?",
                "What length and format are expected?",
            )
        )
    if task_type == "other":
        out.append(_t(language, "Quel est l'objectif principal ?", "What is the main objective?"))
    if word_count < 4:
        out.append(
            _t(
                language,
                "Peux-tu préciser le résultat attendu ?",
                "Can you clarify the expected outcome?",
            )
        )
    return _dedupe(out)[:_MAX_LIST]


_SUCCESS_CRITERIA: dict[TaskType, tuple[str, str]] = {
    "code_generation": (
        "Le code s'exécute sans erreur et répond à l'intention.",
        "The code runs without error and satisfies the intent.",
    ),
    "data_analysis": (
        "Les résultats sont corrects, reproductibles et interprétables.",
        "The results are correct, reproducible and interpretable.",
    ),
    "writing": (
        "Le texte couvre l'intention, dans le ton et le format demandés.",
        "The text covers the intent in the requested tone and format.",
    ),
    "qa": (
        "La réponse est exacte et directement liée à la question.",
        "The answer is accurate and directly addresses the question.",
    ),
    "planning": (
        "Le plan est actionnable, ordonné et complet.",
        "The plan is actionable, ordered and complete.",
    ),
    "other": (
        "Le livrable répond à l'intention exprimée.",
        "The deliverable satisfies the stated intent.",
    ),
}


def _success_criteria(task_type: TaskType, language: str) -> list[str]:
    fr, en = _SUCCESS_CRITERIA[task_type]
    return [_t(language, fr, en)]


def _normalize_goal(intent: str) -> str:
    first = _SENTENCE_SPLIT_RE.split(intent.strip(), maxsplit=1)[0]
    goal = re.sub(r"\s+", " ", first).strip() or intent.strip()
    if len(goal) > _GOAL_MAX:
        goal = goal[: _GOAL_MAX - 1].rstrip() + "…"
    return goal[:1].upper() + goal[1:] if goal else goal


def _confidence(
    task_type: TaskType,
    entities: list[str],
    inputs: list[str],
    constraints: list[str],
    open_questions: list[str],
    word_count: int,
) -> float:
    score = 0.35
    if task_type != "other":
        score += 0.20
    if entities:
        score += 0.10
    if constraints:
        score += 0.10
    if inputs:
        score += 0.10
    if word_count >= 8:
        score += 0.10
    elif word_count < 4:
        score -= 0.15
    score -= 0.05 * len(open_questions)
    return round(max(0.05, min(0.98, score)), 2)


def analyze_intent(intent: str, context: dict[str, Any] | None = None) -> Catr:
    """Analyze a raw human intent into a deterministic CATR (heuristic-v1).

    ``context`` is accepted for forward-compatibility (e.g. caller-provided hints)
    but the heuristic analyzer does not consume it yet.
    """
    _ = context  # reserved; not used by the heuristic analyzer
    text = intent.strip()
    lower = text.lower()
    word_count = len(text.split())

    language = _detect_language(text, lower)
    task_type = _classify_task_type(lower)
    entities = _extract_entities(text, lower)
    inputs = _extract_inputs(text, lower, language)
    constraints = _extract_constraints(text, lower, language)
    assumptions = _derive_assumptions(task_type, language, entities, lower)
    open_questions = _derive_open_questions(
        task_type, language, entities, inputs, constraints, word_count, lower
    )
    success_criteria = _success_criteria(task_type, language)
    confidence = _confidence(task_type, entities, inputs, constraints, open_questions, word_count)

    return Catr(
        goal=_normalize_goal(text),
        task_type=task_type,
        language=language,
        entities=entities,
        inputs=inputs,
        constraints=constraints,
        assumptions=assumptions,
        open_questions=open_questions,
        success_criteria=success_criteria,
        confidence=confidence,
    )

"""Deterministic, offline heuristics for the Intent Engine.

HEURISTIC, NOT AI/LLM. Pure rule-based text analysis (keyword classification, pattern
extraction, small bilingual fr/en templates) that builds a full
:class:`~app.schemas.catr.CanonicalAITask`. Fully deterministic (same input → same
output), no API key, no network — unit-testable in isolation. The emitted CATR carries
``meta.method == "heuristic-v1"``. The Intent Engine may then refine it with a light
LLM only when ``meta.confidence`` is low (see ``app.engines.intent``).
"""

from __future__ import annotations

import re
from typing import Literal

from app.schemas.catr import CanonicalAITask, CatrMeta, Complexity, MissingInformation, Risk

# Internal task taxonomy (drives domain + templates); NOT a CATR field.
TaskType = Literal["code_generation", "data_analysis", "writing", "planning", "qa", "other"]

# Order is also the tie-break priority when keyword scores are equal.
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

_DOMAIN: dict[TaskType, str] = {
    "code_generation": "software",
    "data_analysis": "data",
    "writing": "writing",
    "planning": "product",
    "qa": "general",
    "other": "general",
}

_EXPECTED_OUTPUT: dict[TaskType, tuple[str, str]] = {
    "code_generation": (
        "Code fonctionnel conforme à l'objectif",
        "Working code meeting the objective",
    ),
    "data_analysis": (
        "Une analyse avec des résultats interprétables",
        "An analysis with interpretable results",
    ),
    "writing": ("Un texte rédigé dans le format demandé", "Written text in the requested format"),
    "qa": ("Une réponse claire et exacte", "A clear, accurate answer"),
    "planning": ("Un plan d'action ordonné", "An ordered action plan"),
}

_PEOPLE = (
    "utilisateurs",
    "clients",
    "développeurs",
    "étudiants",
    "débutants",
    "managers",
    "équipe",
    "lecteurs",
    "enfants",
    "users",
    "customers",
    "developers",
    "students",
    "beginners",
    "team",
    "readers",
    "children",
)

_RISK_HIGH = (
    "production",
    "prod",
    "supprime",
    "supprimer",
    "delete",
    "drop table",
    "paiement",
    "payment",
    "mot de passe",
    "password",
    "rgpd",
    "gdpr",
    "données personnelles",
    "irréversible",
    "irreversible",
    "migration",
)
_RISK_MEDIUM = (
    "déploie",
    "déployer",
    "deploy",
    "base de données",
    "database",
    "authentification",
    "authentication",
    "sécurité",
    "security",
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
_VAGUE_TOKENS = frozenset(
    "ça ca truc trucs chose choses machin it this that stuff thing things".split()
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
_PURPOSE_MARKERS: tuple[str, ...] = (
    "afin de",
    "afin d'",
    "parce que",
    "because",
    "so that",
    "in order to",
    "dans le cadre de",
    "pour que",
)

_FILE_RE = re.compile(r"\b[\w\-./]+\.(?:csv|json|txt|xlsx|pdf|md|parquet|sql|ya?ml)\b", re.I)
_URL_RE = re.compile(r"https?://\S+")
_QUOTED_RE = re.compile(r"[\"'«“]([^\"'»”]{1,80})[\"'»”]")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_SENTENCE_SPLIT_RE = re.compile(r"[.?!\n]+")
_CLAUSE_SPLIT_RE = re.compile(r"[,;.\n]+")
_SUBGOAL_SPLIT_RE = re.compile(r"\b(?:et|puis|ensuite|and|then)\b|[;,]", re.I)
_AUDIENCE_RE = re.compile(
    r"(?:pour|for|à destination de)\s+([\w' ’-]{0,30}?(?:" + "|".join(_PEOPLE) + r")\w*)",
    re.I,
)

_MAX_LIST = 12
_GOAL_MAX = 200


def _t(language: str, fr: str, en: str) -> str:
    return fr if language == "fr" else en


def _dedupe(items: list[str]) -> list[str]:
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
    return "fr" if fr > en else "en"


def _classify_task_type(lower: str) -> TaskType:
    scores: dict[TaskType, int] = {
        tt: sum(1 for kw in kws if kw in lower) for tt, kws in TASK_KEYWORDS.items()
    }
    if "?" in lower:
        scores["qa"] = scores.get("qa", 0) + 1
    best = max(scores.values())
    if best == 0:
        return "other"
    for task_type in TASK_KEYWORDS:  # dict order = tie-break priority
        if scores[task_type] == best:
            return task_type
    return "other"


def _normalize_goal(intent: str) -> str:
    first = _SENTENCE_SPLIT_RE.split(intent.strip(), maxsplit=1)[0]
    goal = re.sub(r"\s+", " ", first).strip() or intent.strip()
    if len(goal) > _GOAL_MAX:
        goal = goal[: _GOAL_MAX - 1].rstrip() + "…"
    return goal[:1].upper() + goal[1:] if goal else goal


def _sub_goals(text: str) -> list[str]:
    parts = [re.sub(r"\s+", " ", p).strip() for p in _SUBGOAL_SPLIT_RE.split(text)]
    meaningful = [p for p in parts if len(p.split()) >= 2]
    return _dedupe(meaningful)[:6] if len(meaningful) >= 2 else []


def _has_programming_signal(entities: list[str], lower: str) -> bool:
    langs = {"python", "javascript", "typescript", "java", "golang", "rust"}
    if any(e.lower() in langs for e in entities):
        return True
    return any(re.search(rf"\b{re.escape(t)}\b", lower) for t in langs)


def _extract_entities(text: str, lower: str) -> list[str]:
    found: list[str] = [m.group(1).strip() for m in _QUOTED_RE.finditer(text)]
    found += [tok for tok in TECH_TOKENS if re.search(rf"\b{re.escape(tok)}\b", lower)]
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        for word in sentence.strip().split()[1:]:
            cleaned = word.strip(".,;:!?()[]\"'")
            if len(cleaned) > 1 and cleaned[0].isupper() and cleaned.lower() not in _FR_STOPWORDS:
                found.append(cleaned)
    return _dedupe(found)[:_MAX_LIST]


def _extract_inputs(text: str, lower: str, language: str) -> list[str]:
    found: list[str] = _URL_RE.findall(text)
    found += [m.group(0) for m in _FILE_RE.finditer(text)]
    if any(kw in lower for kw in _INPUT_KEYWORDS):
        found.append(_t(language, "contenu fourni par l'utilisateur", "user-provided content"))
    return _dedupe(found)[:_MAX_LIST]


def _extract_context(text: str, lower: str, entities: list[str], language: str) -> list[str]:
    found: list[str] = []
    for clause in _CLAUSE_SPLIT_RE.split(text):
        c = clause.strip()
        if c and any(marker in c.lower() for marker in _PURPOSE_MARKERS):
            found.append(c)
    tech = [e for e in entities if e.lower() in TECH_TOKENS]
    if tech:
        found.append(_t(language, "Technologies : ", "Technologies: ") + ", ".join(tech))
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


def _expected_output(task_type: TaskType, language: str) -> str | None:
    tmpl = _EXPECTED_OUTPUT.get(task_type)
    return None if tmpl is None else _t(language, tmpl[0], tmpl[1])


def _audience(text: str) -> str | None:
    match = _AUDIENCE_RE.search(text)
    if match is None:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()[:60] or None


def _risk(lower: str) -> Risk:
    if any(kw in lower for kw in _RISK_HIGH):
        return "high"
    if any(kw in lower for kw in _RISK_MEDIUM):
        return "medium"
    return "low"


def _complexity(
    word_count: int, sub_goals: list[str], constraints: list[str], risk: Risk
) -> Complexity:
    signals = (
        (word_count >= 15) + (len(sub_goals) >= 3) + (len(constraints) >= 3) + (risk == "high")
    )
    if signals >= 2:
        return "high"
    return "medium" if signals == 1 else "low"


def _missing_information(
    task_type: TaskType,
    language: str,
    entities: list[str],
    inputs: list[str],
    constraints: list[str],
    word_count: int,
    lower: str,
) -> list[MissingInformation]:
    out: list[MissingInformation] = []
    if task_type == "code_generation" and not _has_programming_signal(entities, lower):
        out.append(
            MissingInformation(
                label=_t(language, "langage ou framework cible", "target language or framework"),
                importance="high",
            )
        )
    if task_type == "data_analysis" and not inputs:
        out.append(
            MissingInformation(
                label=_t(language, "source des données", "data source"), importance="high"
            )
        )
    if task_type == "writing" and not constraints:
        out.append(
            MissingInformation(
                label=_t(language, "longueur et format attendus", "expected length and format"),
                importance="medium",
            )
        )
    if task_type == "other" or word_count < 4:
        out.append(
            MissingInformation(
                label=_t(language, "objectif précis", "precise objective"), importance="high"
            )
        )
    # De-duplicate by label while preserving order.
    seen: set[str] = set()
    unique: list[MissingInformation] = []
    for item in out:
        if item.label not in seen:
            seen.add(item.label)
            unique.append(item)
    return unique[:_MAX_LIST]


def _ambiguities(task_type: TaskType, language: str, word_count: int, lower: str) -> list[str]:
    out: list[str] = []
    if word_count < 4:
        out.append(
            _t(
                language,
                "Intention très courte, peu de détails.",
                "Very short intent, few details.",
            )
        )
    if any(tok in _VAGUE_TOKENS for tok in _WORD_RE.findall(lower)):
        out.append(
            _t(
                language,
                "Référence vague (p. ex. « ça », « truc »).",
                "Vague reference (e.g. 'it', 'stuff').",
            )
        )
    if task_type == "other":
        out.append(_t(language, "Type de tâche indéterminé.", "Undetermined task type."))
    return _dedupe(out)[:_MAX_LIST]


def _confidence(
    task_type: TaskType,
    entities: list[str],
    inputs: list[str],
    constraints: list[str],
    missing: list[MissingInformation],
    ambiguities: list[str],
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
    score -= 0.05 * len(missing)
    score -= 0.05 * len(ambiguities)
    return round(max(0.05, min(0.98, score)), 2)


def build_heuristic_catr(intent: str) -> CanonicalAITask:
    """Build a full CATR from heuristics alone (``meta.method == "heuristic-v1"``)."""
    text = intent.strip()
    lower = text.lower()
    word_count = len(text.split())

    language = _detect_language(text, lower)
    task_type = _classify_task_type(lower)
    entities = _extract_entities(text, lower)
    inputs = _extract_inputs(text, lower, language)
    constraints = _extract_constraints(text, lower, language)
    context = _extract_context(text, lower, entities, language)
    sub_goals = _sub_goals(text)
    risk = _risk(lower)
    missing = _missing_information(
        task_type, language, entities, inputs, constraints, word_count, lower
    )
    ambiguities = _ambiguities(task_type, language, word_count, lower)
    confidence = _confidence(
        task_type, entities, inputs, constraints, missing, ambiguities, word_count
    )

    return CanonicalAITask(
        objective=_normalize_goal(text),
        sub_goals=sub_goals,
        domain=_DOMAIN[task_type],
        inputs=inputs,
        context=context,
        constraints=constraints,
        expected_output=_expected_output(task_type, language),
        audience=_audience(text),
        complexity=_complexity(word_count, sub_goals, constraints, risk),
        missing_information=missing,
        ambiguities=ambiguities,
        risk=risk,
        meta=CatrMeta(method="heuristic-v1", confidence=confidence, enriched_by_llm=False),
    )

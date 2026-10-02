"""Kompilo error taxonomy + the detect→classify→repair→retry→fallback→verify strategy.

A single, explicit taxonomy so every failure gets a stable category, a USER-FRIENDLY
message (French, actionable), an HTTP status, and a retryable flag. The Gateway uses
``classify_exception`` to decide whether to retry a model, fall back to the next, or stop
early (a policy/validation failure is not worth retrying). Routes turn a ``KompiloError``
into a clean response via ``to_http`` — never leaking a stack trace or a secret.

The six-stage strategy, and where each stage lives:
- **detect**   catch the exception / inspect the output (Gateway, Verifier).
- **classify** map it to an ``ErrorCategory`` (``classify_exception``).
- **repair**   attempt a corrective step for recoverable cases (Executor, JSON contracts).
- **retry**    re-attempt retryable categories with backoff (Gateway).
- **fallback** move to the next routed model when a model keeps failing (Gateway).
- **verify**   validate the final output against its contract (Verifier).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCategory(StrEnum):
    INPUT = "INPUT"  # malformed/empty user input
    PROMPT = "PROMPT"  # prompt could not be compiled/assembled
    MODEL = "MODEL"  # provider/model failure (bad response, auth, 5xx)
    TOOL = "TOOL"  # a tool/function call failed
    CONTEXT = "CONTEXT"  # context missing or too large for the window
    POLICY = "POLICY"  # content policy / safety refusal
    TIMEOUT = "TIMEOUT"  # the request timed out
    RATE_LIMIT = "RATE_LIMIT"  # provider throttling
    VALIDATION = "VALIDATION"  # output did not meet its contract (schema/format)
    UNKNOWN = "UNKNOWN"  # anything unclassified


@dataclass(frozen=True, slots=True)
class _Policy:
    retryable: bool
    http_status: int
    user_message: str


# Per-category behavior. User messages are French, specific, and actionable — safe to
# show to an end user (no internals, no secrets).
_POLICIES: dict[ErrorCategory, _Policy] = {
    ErrorCategory.INPUT: _Policy(
        False, 422, "La demande est incomplète ou mal formée. Reformule ta tâche et réessaie."
    ),
    ErrorCategory.PROMPT: _Policy(
        False, 400, "La compilation du prompt a échoué. Précise ton intention et réessaie."
    ),
    ErrorCategory.MODEL: _Policy(
        True, 502, "Le modèle est momentanément indisponible. Un autre modèle a été tenté."
    ),
    ErrorCategory.TOOL: _Policy(
        True, 502, "Un outil appelé pendant l'exécution a échoué. Nouvelle tentative effectuée."
    ),
    ErrorCategory.CONTEXT: _Policy(
        False, 413, "Le contexte est trop volumineux ou manquant. Réduis-le ou fournis la source."
    ),
    ErrorCategory.POLICY: _Policy(
        False, 403, "La demande a été refusée par la politique de contenu du modèle."
    ),
    ErrorCategory.TIMEOUT: _Policy(
        True, 504, "Le modèle a mis trop de temps à répondre. Nouvelle tentative effectuée."
    ),
    ErrorCategory.RATE_LIMIT: _Policy(
        True, 429, "Trop de requêtes vers le modèle. Patiente quelques instants puis réessaie."
    ),
    ErrorCategory.VALIDATION: _Policy(
        False, 422, "La sortie ne respecte pas le format demandé. Vois le rapport de vérification."
    ),
    ErrorCategory.UNKNOWN: _Policy(
        False, 500, "Une erreur inattendue est survenue. Réessaie ; si cela persiste, signale-le."
    ),
}


def is_retryable(category: ErrorCategory) -> bool:
    return _POLICIES[category].retryable


def user_message(category: ErrorCategory) -> str:
    return _POLICIES[category].user_message


def http_status(category: ErrorCategory) -> int:
    return _POLICIES[category].http_status


class KompiloError(Exception):
    """A classified Kompilo failure carrying a user-safe message and HTTP mapping."""

    def __init__(
        self,
        category: ErrorCategory,
        *,
        detail: str = "",
        user_msg: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.category = category
        self.detail = detail  # internal, for logs — NEVER shown to the user
        self.user_message = user_msg or user_message(category)
        self.retryable = is_retryable(category)
        self.http_status = http_status(category)
        super().__init__(f"{category}: {detail or self.user_message}")
        if cause is not None:
            self.__cause__ = cause

    def to_http(self) -> tuple[int, dict[str, str | bool]]:
        """Return ``(status_code, body)`` for an API error response (no internals)."""
        return self.http_status, {
            "category": str(self.category),
            "message": self.user_message,
            "retryable": self.retryable,
        }


# Substring hints for classifying a provider/transport error from its message.
_HINTS: tuple[tuple[tuple[str, ...], ErrorCategory], ...] = (
    (("rate limit", "rate_limit", "429", "too many requests", "throttl"), ErrorCategory.RATE_LIMIT),
    (("timeout", "timed out", "deadline"), ErrorCategory.TIMEOUT),
    (("content policy", "safety", "moderation", "content_filter"), ErrorCategory.POLICY),
    (
        ("context length", "maximum context", "too many tokens", "token limit"),
        ErrorCategory.CONTEXT,
    ),
    (("401", "403", "unauthorized", "forbidden", "api key", "authentication"), ErrorCategory.MODEL),
    (("tool", "function call"), ErrorCategory.TOOL),
)


def classify_exception(exc: BaseException) -> ErrorCategory:
    """Map an arbitrary exception to a stable category (detect → classify)."""
    if isinstance(exc, KompiloError):
        return exc.category
    # In Python 3.11+ asyncio.TimeoutError is an alias of the builtin TimeoutError.
    if isinstance(exc, TimeoutError):
        return ErrorCategory.TIMEOUT
    message = str(exc).lower()
    for needles, category in _HINTS:
        if any(n in message for n in needles):
            return category
    # A bare provider/transport failure with no clearer signal → MODEL (retryable).
    if exc.__class__.__name__ in {"ProviderError", "GatewayError"}:
        return ErrorCategory.MODEL
    return ErrorCategory.UNKNOWN

"""Provider protocol — the narrow contract the Intent Engine depends on.

Kept deliberately tiny so the future Gateway can implement the same ``Protocol``
(adding routing, budgets, fallbacks, caching) without touching callers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Any failure talking to a provider (network, auth, bad response)."""


@runtime_checkable
class LLMProvider(Protocol):
    #: Stable identifier for logs/telemetry (e.g. "openai-compatible").
    name: str

    async def complete_json(self, *, system: str, user: str, max_tokens: int = 400) -> str:
        """Return the model's raw text completion (expected to be a JSON object).

        Implementations should request JSON output and raise ``ProviderError`` on any
        transport/auth/decoding failure so the caller can fall back cleanly.
        """
        ...

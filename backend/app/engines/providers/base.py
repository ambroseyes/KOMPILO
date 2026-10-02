"""Model Abstraction Layer — the provider contract the Gateway depends on.

One narrow interface (`complete` + `capabilities`) so any backend — OpenAI, Ollama,
LM Studio, or an offline stub — is interchangeable behind the Gateway. Keys and base
URLs are read from the environment by the provider factory, never hardcoded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Any failure talking to a provider (network, auth, bad response)."""


@dataclass(frozen=True, slots=True)
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider: str
    supports_streaming: bool
    is_real: bool  # False for the offline stub — surfaced so nothing is faked silently
    note: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    #: Stable identifier for logs/telemetry (e.g. "openai-compatible", "echo-offline").
    name: str

    def capabilities(self) -> ProviderCapabilities:
        """Describe what this provider can do (streaming, whether it is a real model)."""
        ...

    async def complete(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> CompletionResult:
        """Produce a completion, returning text + token usage. Raise ``ProviderError``
        on any transport/auth/decoding failure so the Gateway can retry or fall back."""
        ...

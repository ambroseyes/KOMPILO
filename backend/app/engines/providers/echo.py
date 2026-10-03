"""EchoProvider — a deterministic, offline STUB provider.

NOT A REAL MODEL. Used when no API key is configured so execution is runnable and
testable offline, and as the fake in tests. It returns a deterministic response derived
from the prompt (valid JSON when ``json_mode`` is requested) and approximate token
counts. Its ``capabilities().is_real`` is ``False`` and every response is marked, so the
executor/Gateway can flag that the output is a stub, never a real completion.
"""

from __future__ import annotations

import json

from app.engines.providers.base import CompletionResult, ProviderCapabilities

_STUB_TAG = "[echo-offline STUB — not a real model]"


def _approx_tokens(*texts: str) -> int:
    return max(1, sum(len(t) for t in texts) // 4)


class EchoProvider:
    name = "echo-offline"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_streaming=True,
            is_real=False,
            note="Deterministic offline stub — set OPENAI_API_KEY for a real model.",
        )

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
        head = prompt.strip().splitlines()[0][:200] if prompt.strip() else ""
        if json_mode:
            text = json.dumps(
                {"result": head, "generated_by": "echo-offline-stub", "ok": True},
                ensure_ascii=False,
            )
        else:
            text = f"{_STUB_TAG} (model={model})\n\n{head}"
        return CompletionResult(
            text=text,
            input_tokens=_approx_tokens(system or "", prompt),
            output_tokens=_approx_tokens(text),
            model=model,
            provider=self.name,
        )

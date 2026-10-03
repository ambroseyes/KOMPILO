"""Embedding providers — the vector port behind RAG retrieval.

Mirrors the completion providers' honesty policy: a real OpenAI-compatible embedder
(``POST {base_url}/embeddings``) when a key is configured, or a deterministic **offline
hash embedder** (``is_real == False``) otherwise, so ingestion and retrieval are runnable
offline and in tests. Offline vectors are a lexical hashing proxy — NOT semantic
embeddings — and every result is flagged so a ranking produced over them is never
presented as meaningful.

All vectors have a fixed dimension ``EMBEDDING_DIM`` so a single ``vector`` column works
for both backends. Real embeddings are requested at that dimension (``dimensions`` param,
supported by ``text-embedding-3-*``); a backend that returns another size is rejected
loudly rather than silently corrupting the index.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from app.engines.providers.base import ProviderError

# Fixed vector dimension for the corpus. Changing it requires a new migration that
# re-creates the ``document_chunks.embedding`` column — keep it in sync with 0012.
EMBEDDING_DIM = 1536

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Shown whenever retrieval ran over offline (non-semantic) embeddings.
OFFLINE_NOTE = (
    "Embeddings hors-ligne (proxy lexical déterministe, PAS sémantique) : la pertinence "
    "n'est pas significative. Configure OPENAI_API_KEY pour de vrais embeddings."
)


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    provider: str
    is_real: bool
    input_tokens: int = 0
    note: str = ""


@runtime_checkable
class Embedder(Protocol):
    name: str
    is_real: bool

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed each text into an ``EMBEDDING_DIM``-vector. Raise ``ProviderError`` on
        any transport/decoding failure or a dimension mismatch."""
        ...


def _hash_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic lexical hashing vectorizer (signed hashing trick), L2-normalized.

    Not semantic — two texts are "close" only when they share tokens. Deterministic and
    reproducible, which is exactly what the offline honesty contract needs.
    """
    vec = [0.0] * dim
    for tok in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.sha1(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        vec[idx] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0.0:
        vec = [v / norm for v in vec]
    return vec


class OfflineHashEmbedder:
    """Offline STUB embedder — deterministic, no network. ``is_real == False``."""

    name = "offline-hash"
    is_real = False

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[_hash_embed(t) for t in texts],
            model=self.name,
            provider=self.name,
            is_real=False,
            input_tokens=0,
            note=OFFLINE_NOTE,
        )


class OpenAICompatibleEmbedder:
    """Real embeddings via ``POST {base_url}/embeddings`` (OpenAI schema)."""

    name = "openai-compatible"
    is_real = True

    def __init__(
        self, *, api_key: str, base_url: str, model: str, timeout_seconds: float = 30.0
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=self._model, provider=self.name, is_real=True)
        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
            "dimensions": EMBEDDING_DIM,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
            items = sorted(data["data"], key=lambda d: int(d["index"]))
            vectors = [[float(x) for x in item["embedding"]] for item in items]
            usage = data.get("usage") or {}
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            # Never leak the key or raw provider internals upward.
            raise ProviderError(f"{self.name} embeddings failed: {type(exc).__name__}") from exc
        if len(vectors) != len(texts):
            raise ProviderError(f"{self.name} returned {len(vectors)} vectors for {len(texts)}")
        for vec in vectors:
            if len(vec) != EMBEDDING_DIM:
                raise ProviderError(
                    f"{self.name} returned dim {len(vec)}, expected {EMBEDDING_DIM}"
                )
        return EmbeddingResult(
            vectors=vectors,
            model=self._model,
            provider=self.name,
            is_real=True,
            input_tokens=int(usage.get("prompt_tokens", 0)),
        )

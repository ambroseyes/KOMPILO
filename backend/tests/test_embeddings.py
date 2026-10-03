"""Unit tests for the offline hash embedder (deterministic, flagged not-real)."""

from __future__ import annotations

import math

import pytest

from app.engines.providers import get_embedder
from app.engines.providers.embeddings import (
    EMBEDDING_DIM,
    OFFLINE_NOTE,
    OfflineHashEmbedder,
)


@pytest.mark.asyncio
async def test_offline_embedder_is_deterministic_and_correct_dim() -> None:
    emb = OfflineHashEmbedder()
    a = await emb.embed(["bienvenue nouveau client"])
    b = await emb.embed(["bienvenue nouveau client"])
    assert a.vectors == b.vectors
    assert len(a.vectors[0]) == EMBEDDING_DIM


@pytest.mark.asyncio
async def test_offline_vectors_are_unit_normalized() -> None:
    (vec,) = (await OfflineHashEmbedder().embed(["des mots porteurs de sens"])).vectors
    assert math.isclose(math.sqrt(sum(v * v for v in vec)), 1.0, rel_tol=1e-6)


@pytest.mark.asyncio
async def test_offline_embedder_is_flagged_not_real() -> None:
    result = await OfflineHashEmbedder().embed(["x"])
    assert result.is_real is False
    assert result.note == OFFLINE_NOTE


@pytest.mark.asyncio
async def test_shared_tokens_are_closer_than_disjoint_ones() -> None:
    emb = OfflineHashEmbedder()
    res = await emb.embed(["chat chien oiseau", "chat chien tortue", "banane pomme kiwi"])
    base, near, far = res.vectors

    def cos(u: list[float], v: list[float]) -> float:
        return sum(x * y for x, y in zip(u, v, strict=True))

    # Two tokens shared vs none shared → the overlapping pair is strictly closer.
    assert cos(base, near) > cos(base, far)


def test_factory_returns_offline_without_key() -> None:
    # In the test environment no OPENAI_API_KEY is set → offline embedder.
    assert isinstance(get_embedder(), OfflineHashEmbedder)

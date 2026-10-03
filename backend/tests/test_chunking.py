"""Unit tests for the deterministic corpus chunker."""

from __future__ import annotations

import pytest

from app.engines.chunking import chunk_text


def test_short_text_is_a_single_chunk() -> None:
    assert chunk_text("Bonjour le monde") == ["Bonjour le monde"]


def test_empty_and_blank_text_yields_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  \t ") == []


def test_paragraphs_are_packed_up_to_max_chars() -> None:
    text = "\n\n".join(["a" * 40, "b" * 40, "c" * 40])
    chunks = chunk_text(text, max_chars=100)
    # 40 + 2 + 40 = 82 fits; adding the third (+2+40) would exceed 100 → new chunk.
    assert chunks == [f"{'a' * 40}\n\n{'b' * 40}", "c" * 40]
    assert all(len(c) <= 100 for c in chunks)


def test_oversize_paragraph_is_hard_split() -> None:
    chunks = chunk_text("x" * 250, max_chars=100)
    assert chunks == ["x" * 100, "x" * 100, "x" * 50]


def test_is_deterministic() -> None:
    text = "Para one.\n\nPara two is a little longer.\n\nPara three."
    assert chunk_text(text, max_chars=30) == chunk_text(text, max_chars=30)


def test_invalid_max_chars_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_text("anything", max_chars=0)

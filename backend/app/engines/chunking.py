"""Deterministic text chunking for corpus ingestion.

Paragraph-aware packing: paragraphs (blank-line separated) are packed into chunks up to
``max_chars``; a paragraph longer than ``max_chars`` is hard-split on a character window.
Deterministic and dependency-free so it is trivially unit-testable. No overlap in v1
(documented limit) — good enough to retrieve the right chunk for a focused query.
"""

from __future__ import annotations

import re

_DEFAULT_MAX_CHARS = 1000
_PARAGRAPH_RE = re.compile(r"\n\s*\n")


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def chunk_text(text: str, *, max_chars: int = _DEFAULT_MAX_CHARS) -> list[str]:
    """Split ``text`` into a deterministic list of non-empty chunks (each ≤ ``max_chars``)."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    paragraphs = [p.strip() for p in _PARAGRAPH_RE.split(text.strip()) if p.strip()]

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(para, max_chars))
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > max_chars:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks

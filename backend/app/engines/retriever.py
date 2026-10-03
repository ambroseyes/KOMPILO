"""Retriever — embed a query and fetch the closest corpus chunks for the current tenant.

Holds a tenant-pinned ``AsyncSession`` (RLS confines every read to the tenant) and an
``Embedder``. Retrieval embeds the query, then orders ``document_chunks`` by cosine
distance (pgvector ``<=>`` via ``cosine_distance``) and returns the top-k with a
similarity score. ``is_real`` propagates from the embedder so a ranking over offline
(non-semantic) vectors is flagged, never presented as meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.providers import Embedder, get_embedder
from app.engines.providers.embeddings import OFFLINE_NOTE
from app.models.documents import Document, DocumentChunk

_DEFAULT_K = 4


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    document_id: str
    document_title: str
    chunk_id: str
    chunk_index: int
    content: str
    score: float  # cosine similarity in [-1, 1]; higher = closer


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    is_real: bool = False
    note: str = ""


class Retriever:
    def __init__(self, session: AsyncSession, embedder: Embedder | None = None) -> None:
        self._session = session
        self._embedder = embedder or get_embedder()

    async def retrieve(self, query: str, *, k: int = _DEFAULT_K) -> RetrievalResult:
        if not query.strip() or k <= 0:
            return RetrievalResult(chunks=[], is_real=self._embedder.is_real, note="")
        embedding = await self._embedder.embed([query])
        qvec = embedding.vectors[0]

        distance = DocumentChunk.embedding.cosine_distance(qvec)
        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                Document.title,
                distance.label("distance"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.deleted_at.is_(None))
            .order_by(distance)
            .limit(k)
        )
        rows = (await self._session.execute(stmt)).all()
        chunks = [
            RetrievedChunk(
                document_id=str(row.document_id),
                document_title=row.title,
                chunk_id=str(row.id),
                chunk_index=int(row.chunk_index),
                content=row.content,
                score=round(1.0 - float(row.distance), 4),
            )
            for row in rows
        ]
        note = "" if self._embedder.is_real else OFFLINE_NOTE
        return RetrievalResult(chunks=chunks, is_real=self._embedder.is_real, note=note)

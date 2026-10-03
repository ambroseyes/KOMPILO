"""Corpus ingestion — chunk a document, embed each chunk, persist (tenant-scoped).

Pure service used by the documents route and tests. ``tenant_id`` / ``created_by`` are
always set from the authenticated caller, never from client input (the RLS ``WITH CHECK``
is the backstop). Embeddings come from the injected/factory ``Embedder`` — real when a key
is set, otherwise the offline hash STUB (flagged on the document via ``embedding_is_real``
so a later ranking over offline vectors is never presented as meaningful).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.chunking import chunk_text
from app.engines.providers import Embedder, get_embedder
from app.models.documents import Document, DocumentChunk


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    document: Document
    n_chunks: int
    embedding_is_real: bool
    note: str


async def ingest_document(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID | None,
    title: str,
    content: str,
    source_uri: str | None = None,
    embedder: Embedder | None = None,
) -> IngestOutcome:
    embedder = embedder or get_embedder()
    chunks = chunk_text(content)
    embedding = await embedder.embed(chunks)

    document = Document(
        tenant_id=tenant_id,
        created_by=created_by,
        title=title,
        source_uri=source_uri,
        embedding_model=embedding.model,
        embedding_is_real=embedding.is_real,
    )
    session.add(document)
    await session.flush()  # assign document.id

    for index, (text, vector) in enumerate(zip(chunks, embedding.vectors, strict=True)):
        session.add(
            DocumentChunk(
                tenant_id=tenant_id,
                document_id=document.id,
                chunk_index=index,
                content=text,
                embedding=vector,
            )
        )
    await session.flush()
    return IngestOutcome(
        document=document,
        n_chunks=len(chunks),
        embedding_is_real=embedding.is_real,
        note=embedding.note,
    )

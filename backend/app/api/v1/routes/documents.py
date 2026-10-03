"""RAG corpus API — ingest documents and search the tenant's corpus.

All routes are authenticated and tenant-scoped (RLS via ``TenantSession``). ``tenant_id``
and ``created_by`` are derived from the token, never the request body. Search embeds the
query and returns the closest chunks with an honesty flag: offline (non-semantic)
embeddings yield a ``note`` and ``is_real=false`` so the ranking is never taken as real.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, TenantSession, get_current_user
from app.engines.retriever import Retriever
from app.models.documents import Document
from app.schemas.documents import (
    DocumentCreate,
    DocumentRead,
    IngestResult,
    RetrievedChunkRead,
    SearchRequest,
    SearchResult,
)
from app.services.ingestion import ingest_document

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/documents", response_model=IngestResult, status_code=201)
async def create_document(
    payload: DocumentCreate, user: CurrentUser, db: TenantSession
) -> IngestResult:
    outcome = await ingest_document(
        db,
        tenant_id=user.tenant_id,
        created_by=user.id,
        title=payload.title,
        content=payload.content,
        source_uri=payload.source_uri,
    )
    await db.refresh(outcome.document)
    return IngestResult(
        document=DocumentRead.model_validate(outcome.document),
        n_chunks=outcome.n_chunks,
        embedding_is_real=outcome.embedding_is_real,
        note=outcome.note,
    )


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(db: TenantSession) -> list[Document]:
    stmt = (
        select(Document).where(Document.deleted_at.is_(None)).order_by(Document.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: uuid.UUID, db: TenantSession) -> Document:
    document = await db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, db: TenantSession) -> None:
    document = await db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
    document.deleted_at = func.now()
    await db.flush()


@router.post("/documents/search", response_model=SearchResult)
async def search_documents(payload: SearchRequest, db: TenantSession) -> SearchResult:
    result = await Retriever(db).retrieve(payload.query, k=payload.k)
    return SearchResult(
        query=payload.query,
        chunks=[
            RetrievedChunkRead(
                document_id=uuid.UUID(c.document_id),
                document_title=c.document_title,
                chunk_id=uuid.UUID(c.chunk_id),
                chunk_index=c.chunk_index,
                content=c.content,
                score=c.score,
            )
            for c in result.chunks
        ],
        is_real=result.is_real,
        note=result.note,
    )

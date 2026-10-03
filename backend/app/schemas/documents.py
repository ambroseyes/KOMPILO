"""Schemas for the RAG corpus API (ingestion + retrieval)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    source_uri: str | None = Field(default=None, max_length=1000)


class DocumentRead(BaseModel):
    id: uuid.UUID
    title: str
    source_uri: str | None
    embedding_model: str
    embedding_is_real: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestResult(BaseModel):
    document: DocumentRead
    n_chunks: int
    embedding_is_real: bool
    note: str = ""


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=4, ge=1, le=20)


class RetrievedChunkRead(BaseModel):
    document_id: uuid.UUID
    document_title: str
    chunk_id: uuid.UUID
    chunk_index: int
    content: str
    score: float


class SearchResult(BaseModel):
    query: str
    chunks: list[RetrievedChunkRead]
    is_real: bool
    note: str = ""

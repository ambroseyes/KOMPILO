"""Corpus models for RAG — tenant-scoped documents and their embedded chunks.

A ``Document`` is a piece of source material a tenant ingests; it is split into
``DocumentChunk`` rows, each carrying a fixed-dimension ``embedding`` (pgvector) used for
similarity retrieval. Both tables are TENANT-SCOPED — their RLS policies are created in
migration ``0012_documents`` (see the ``kompilo-rls`` skill). ``embedding_model`` /
``embedding_is_real`` record which embedding space a document lives in, so a ranking over
offline (non-semantic) vectors is never silently presented as meaningful.
"""

from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.engines.providers.embeddings import EMBEDDING_DIM
from app.models.base import (
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Document(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    """TENANT-SCOPED — RLS policy created in migration 0012."""

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_tenant_id_created_at", "tenant_id", "created_at"),)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Which embedding space the chunks live in, and whether it is a real (semantic) model.
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_is_real: Mapped[bool] = mapped_column(Boolean, nullable=False)


class DocumentChunk(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """TENANT-SCOPED — RLS policy created in migration 0012."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_tenant_id_document_id", "tenant_id", "document_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

"""Prompt and PromptVersion (the compiler's versioned content)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Prompt(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "prompts"
    __table_args__ = (
        # PARTIAL unique index: a slug is unique among LIVE prompts of a project, so
        # it can be reused once a prompt is soft-deleted (see migration 0006).
        Index(
            "uq_prompts_tenant_id_project_id_slug",
            "tenant_id",
            "project_id",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_prompts_tenant_id_project_id", "tenant_id", "project_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PromptVersion(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One immutable-ish compiled version of a prompt.

    ``catr``/``ir``/``renders``/``diagnostics`` are JSONB payloads filled as the
    pipeline progresses (nullable until produced).
    """

    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "prompt_id",
            "version",
            name="uq_prompt_versions_tenant_id_prompt_id_version",
        ),
        Index("ix_prompt_versions_tenant_id_prompt_id", "tenant_id", "prompt_id"),
    )

    prompt_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Raw human intent this version compiles from — the input the `understand`
    # stage analyzes into `catr`. Nullable until supplied.
    source_intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    catr: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    ir: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    renders: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    diagnostics: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    model_target: Mapped[str | None] = mapped_column(String(100), nullable=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

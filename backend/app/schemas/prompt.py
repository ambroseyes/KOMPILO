"""Prompt and PromptVersion API schemas (tenant-owned content).

A ``Prompt`` lives inside a ``Project`` (``project_id`` comes from the URL path,
never the body). A ``PromptVersion`` is an append-only, monotonically-numbered
snapshot: ``version`` is allocated server-side, and ``prompt_id`` / ``tenant_id`` /
``author_id`` are derived from context, never from the client (see the
``kompilo-rls`` / ``kompilo-crud`` skills).

A version carries its immutable ``content`` (the versioned prompt source) and,
optionally, the raw ``source_intent`` the ``understand`` stage analyzes into
``catr``. The pipeline payloads (``catr``, ``ir``, ``renders``, ``diagnostics``)
are opaque JSON, optional so a version can be created before the pipeline fills them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


# ── Prompt ───────────────────────────────────────────────────────────────────
class PromptCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=63, pattern=_SLUG_PATTERN)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class PromptUpdate(BaseModel):
    """Partial update; ``name`` cannot be set to ``null`` (NOT NULL in the DB)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)

    @field_validator("name")
    @classmethod
    def _forbid_null_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("name cannot be null; omit it to leave it unchanged")
        return value


class PromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# ── PromptVersion (immutable, append-only) ─────────────────────────────────────
class PromptVersionCreate(BaseModel):
    """Create a new immutable version. ``version`` is assigned by the server.

    ``content`` is the versioned source (required, immutable). ``source_intent`` is
    the optional raw human text the ``understand`` stage analyzes into ``catr``.
    """

    content: str = Field(..., min_length=1)
    source_intent: str | None = Field(default=None, max_length=10_000)
    model_target: str | None = Field(default=None, max_length=100)
    catr: dict[str, Any] | None = None
    ir: dict[str, Any] | None = None
    renders: dict[str, Any] | None = None
    diagnostics: dict[str, Any] | None = None


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    prompt_id: uuid.UUID
    version: int
    content: str
    source_intent: str | None
    model_target: str | None
    catr: Any | None
    ir: Any | None
    renders: Any | None
    diagnostics: Any | None
    author_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

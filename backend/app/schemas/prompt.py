"""Prompt and PromptVersion API schemas (tenant-owned content).

A ``Prompt`` lives inside a ``Project`` (``project_id`` comes from the URL path,
never the body). A ``PromptVersion`` is an append-only, monotonically-numbered
snapshot of a prompt: the ``version`` number is allocated server-side, and
``prompt_id`` / ``tenant_id`` / ``author_id`` are all derived from context, never
from the client (see the ``kompilo-rls`` / ``kompilo-crud`` skills).

The pipeline payloads (``catr``, ``ir``, ``renders``, ``diagnostics``) are opaque
JSON objects for now; their shape is formalized when the real ``understand`` stage
lands. They are optional so a version can be created before the pipeline fills it.
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


# ── PromptVersion ────────────────────────────────────────────────────────────
class PromptVersionCreate(BaseModel):
    # ``version`` is server-allocated (monotonic per prompt) — never client-set.
    # ``source_intent`` is the raw human text the `understand` stage analyzes.
    source_intent: str | None = Field(default=None, max_length=10_000)
    catr: dict[str, Any] | None = None
    ir: dict[str, Any] | None = None
    renders: dict[str, Any] | None = None
    diagnostics: dict[str, Any] | None = None
    model_target: str | None = Field(default=None, max_length=100)


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    prompt_id: uuid.UUID
    version: int
    source_intent: str | None
    catr: dict[str, Any] | None
    ir: dict[str, Any] | None
    renders: dict[str, Any] | None
    diagnostics: dict[str, Any] | None
    model_target: str | None
    author_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

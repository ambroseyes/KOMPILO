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
_MAX_TAGS = 20


def _normalize_tags(tags: list[str] | None) -> list[str]:
    """Lowercase, strip, drop empties, de-duplicate (order-preserving), cap the count."""
    if not tags:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        tag = raw.strip().lower()
        if not tag or tag in seen:
            continue
        if len(tag) > 63:
            raise ValueError(f"tag '{tag[:16]}…' exceeds 63 characters")
        seen.add(tag)
        out.append(tag)
    if len(out) > _MAX_TAGS:
        raise ValueError(f"at most {_MAX_TAGS} tags are allowed")
    return out


# ── Prompt ───────────────────────────────────────────────────────────────────
class PromptCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=63, pattern=_SLUG_PATTERN)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value)


class PromptCreateFlat(PromptCreate):
    """Flat create under ``POST /v1/prompts`` — carries its ``project_id`` in the body.

    (The project-scoped ``POST /projects/{id}/prompts`` takes it from the path instead.)
    """

    project_id: uuid.UUID


class PromptUpdate(BaseModel):
    """Partial update; ``name`` cannot be set to ``null`` (NOT NULL in the DB)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    tags: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _forbid_null_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("name cannot be null; omit it to leave it unchanged")
        return value

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _normalize_tags(value)


class PromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    tags: list[str]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# ── PromptVersion ────────────────────────────────────────────────────────────
class PromptVersionCreate(BaseModel):
    # ``version`` is server-allocated (monotonic per prompt) — never client-set.
    # ``source_intent`` is the raw human text the `understand` stage analyzes.
    # The pipeline payloads are opaque JSON snapshots (objects OR arrays), so they are
    # typed ``Any``: ``catr`` is an object, ``ir``/``diagnostics`` are arrays, etc.
    source_intent: str | None = Field(default=None, max_length=10_000)
    content: str | None = None  # immutable rendered source (optional; compat column)
    catr: Any | None = None
    ir: Any | None = None
    renders: Any | None = None
    diagnostics: Any | None = None
    model_target: str | None = Field(default=None, max_length=100)


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    prompt_id: uuid.UUID
    version: int
    source_intent: str | None
    content: str | None
    catr: Any | None
    ir: Any | None
    renders: Any | None
    diagnostics: Any | None
    model_target: str | None
    author_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

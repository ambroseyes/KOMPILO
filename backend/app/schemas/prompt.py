"""Prompt and PromptVersion API schemas.

``tenant_id`` and ``project_id``/``prompt_id`` are NEVER taken from the request
body — they come from the authenticated tenant and the URL path (see kompilo-rls).

Prompt VERSIONS are immutable: there is no update schema for them. A new revision
is created as a new version (``version`` is server-assigned and monotonic per
prompt); the version's ``content`` never changes once written.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


# ── Prompt ───────────────────────────────────────────────────────────────────
class PromptCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=63, pattern=_SLUG_PATTERN)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class PromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


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


# ── PromptVersion (immutable) ────────────────────────────────────────────────
class PromptVersionCreate(BaseModel):
    """Create a new immutable version. ``version`` is assigned by the server."""

    content: str = Field(..., min_length=1)
    model_target: str | None = Field(default=None, max_length=100)


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    prompt_id: uuid.UUID
    version: int
    content: str
    model_target: str | None
    catr: Any | None
    ir: Any | None
    renders: Any | None
    diagnostics: Any | None
    author_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

"""Artifact API schemas.

Note: ``tenant_id`` is intentionally ABSENT from create/update inputs — it is
derived from the authenticated tenant, never from the client (see kompilo-rls).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ArtifactKind = Literal["strategy", "plan", "report", "other"]


class ArtifactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    kind: ArtifactKind = "other"
    content: dict[str, Any] = Field(default_factory=dict)


class ArtifactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: ArtifactKind | None = None
    content: dict[str, Any] | None = None


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    kind: str
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime

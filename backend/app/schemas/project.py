"""Project API schemas.

``tenant_id`` is intentionally ABSENT from create/update inputs — it is derived
from the authenticated tenant, never from the client (see the kompilo-rls skill).
``slug`` is immutable after creation (stable identity), so it is absent from the
update schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class ProjectCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=63, pattern=_SLUG_PATTERN)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    team_id: uuid.UUID | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    team_id: uuid.UUID | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    team_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

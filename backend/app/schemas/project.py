"""Project API schemas (tenant-owned content).

``tenant_id`` and ``created_by`` are server-derived from the authenticated user,
never accepted from the client (see the ``kompilo-rls`` / ``kompilo-crud`` skills).
``slug`` is immutable after creation — it is the project's stable handle — so it is
absent from the update schema. ``team_id`` is intentionally not exposed yet: teams
have no management endpoints, so accepting one would only produce a broken FK.
"""Project API schemas.

``tenant_id`` is intentionally ABSENT from create/update inputs — it is derived
from the authenticated tenant, never from the client (see the kompilo-rls skill).
``slug`` is immutable after creation (stable identity), so it is absent from the
update schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Lowercase, digit/hyphen handle; must start with an alphanumeric.
from pydantic import BaseModel, ConfigDict, Field

_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class ProjectCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=63, pattern=_SLUG_PATTERN)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)


class ProjectUpdate(BaseModel):
    """Partial update. Only provided fields change (``exclude_unset``).

    ``description`` accepts an explicit ``null`` to clear it; ``name`` is NOT NULL
    in the database, so an explicit ``null`` is rejected (422) rather than causing
    a 500 at flush time.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)

    @field_validator("name")
    @classmethod
    def _forbid_null_name(cls, value: str | None) -> str | None:
        # Only runs when ``name`` is present in the payload (validate_default=False),
        # so omitting it still means "leave unchanged".
        if value is None:
            raise ValueError("name cannot be null; omit it to leave it unchanged")
        return value
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

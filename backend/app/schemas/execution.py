"""Execution API schemas (an async pipeline run over a prompt version).

An execution is a job record: created ``pending``, enqueued to the ARQ worker, then
moved to ``running`` → ``succeeded`` / ``failed``. ``tenant_id`` / ``created_by`` are
server-set; the client only names which prompt version to run and optional context.
For now the only stage dispatched is ``understand`` (reads the version's
``source_intent``, writes its ``catr``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionCreate(BaseModel):
    prompt_version_id: uuid.UUID
    context: dict[str, Any] = Field(default_factory=dict)


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    prompt_version_id: uuid.UUID
    status: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

"""Shared Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    version: str
    db: str  # "ok" | "ko"


class Page[T](BaseModel):
    """A single page of a listing + the cursor echoed back to the caller.

    ``total`` is the full count matching the filters (before limit/offset), so a UI
    can render pagination controls. ``items`` holds at most ``limit`` rows.
    """

    items: list[T]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)

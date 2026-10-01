"""Model registry — import every model here so Alembic autogenerate sees them."""

from app.db.base import Base
from app.models.artifact import Artifact
from app.models.tenant import PipelineRun, Tenant

__all__ = ["Base", "Tenant", "PipelineRun", "Artifact"]

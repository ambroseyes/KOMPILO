"""Model registry — import every model here so Alembic autogenerate sees them."""

from app.db.base import Base
from app.models.artifact import Artifact
from app.models.documents import Document, DocumentChunk
from app.models.execution import Execution
from app.models.execution_step import ExecutionStep
from app.models.organization import Organization
from app.models.project import Project
from app.models.prompt import Prompt, PromptVersion
from app.models.team import Membership, Team
from app.models.user import User

__all__ = [
    "Base",
    "Organization",
    "User",
    "Team",
    "Membership",
    "Project",
    "Prompt",
    "PromptVersion",
    "Execution",
    "ExecutionStep",
    "Artifact",
    "Document",
    "DocumentChunk",
]

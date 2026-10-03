"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.routes import (
    artifacts,
    auth,
    execute,
    executions,
    health,
    organizations,
    projects,
    prompts,
    stream,
)
from app.api.v1.routes import compile as compile_routes

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(compile_routes.router, tags=["compile"])
api_router.include_router(organizations.router, tags=["organizations"])
api_router.include_router(projects.router, tags=["projects"])
api_router.include_router(prompts.router, tags=["prompts"])
api_router.include_router(executions.router, tags=["executions"])
api_router.include_router(stream.router, tags=["executions"])
api_router.include_router(execute.router, tags=["execute"])
api_router.include_router(artifacts.router, tags=["artifacts"])

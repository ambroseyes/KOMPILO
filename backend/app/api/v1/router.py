"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.routes import artifacts, auth, health, organizations
from app.api.v1.routes import compile as compile_routes

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(compile_routes.router, tags=["compile"])
api_router.include_router(organizations.router, tags=["organizations"])
api_router.include_router(artifacts.router, tags=["artifacts"])

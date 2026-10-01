"""API v1 router aggregation."""
from fastapi import APIRouter

from app.api.v1.routes import compile as compile_routes
from app.api.v1.routes import artifacts, health, tenants

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(compile_routes.router, tags=["compile"])
api_router.include_router(tenants.router, tags=["tenants"])
api_router.include_router(artifacts.router, tags=["artifacts"])

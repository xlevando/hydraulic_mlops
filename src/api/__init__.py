"""Роутеры API приложения."""

from fastapi import APIRouter

from src.api.health import health_router
from src.api.version import version_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(version_router)

__all__ = ["api_router"]

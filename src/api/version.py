"""Version-эндпоинт."""

from fastapi import APIRouter, Request

from src.schemas import VersionResponse

version_router = APIRouter(tags=["version"])


@version_router.get("/api/v1/version", response_model=VersionResponse)
async def version(request: Request) -> VersionResponse:
    """Вернуть версию приложения и окружение."""
    settings = request.app.state.settings
    return VersionResponse(
        version=settings.app.version,
        environment=settings.environment,
    )

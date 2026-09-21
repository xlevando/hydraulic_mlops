from fastapi import FastAPI

from src.api import v1_router

# from src.config import Settings
from src.config import get_settings


def create_app() -> FastAPI:
    # settings = Settings()
    settings = get_settings()
    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        description=settings.app.description,
    )

    app.include_router(v1_router)
    return app


app = create_app()

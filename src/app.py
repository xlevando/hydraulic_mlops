import logging

from fastapi import FastAPI

from src.api import v1_router
from src.config import get_settings
from src.logging_config import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    logger.info("Starting %s v%s", settings.app.name, settings.app.version)

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        description=settings.app.description,
    )

    app.include_router(v1_router)
    logger.info("Application configured")
    return app


app = create_app()

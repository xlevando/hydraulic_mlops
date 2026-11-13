"""Точка сборки приложения FastAPI.

Запуск: `uv run uvicorn src.app:app --reload`
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from src import config, db, logging_config
from src.api import api_router
from src.broker import broker  # добавили импорт брокера
from src.services.model_registry import load_champion_models
from src.tracing import setup_tracing

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Жизненный цикл: инициализация БД, RabbitMQ, моделей."""
    settings = config.get_settings()
    logging_config.setup_logging(settings.log_level)

    app.state.settings = settings
    app.state.db_pool = await db.create_db_pool()

    log.info("Загрузка champion-моделей из MLflow")
    app.state.models = load_champion_models()

    log.info(
        "Загружено моделей: %d (%s)",
        len(app.state.models),
        ", ".join(app.state.models),
    )

    # подключить broker для publish
    log.info("Подключение к RabbitMQ")
    await broker.start()

    log.info(
        "Приложение %s v%s запущено (env=%s)",
        settings.app.name,
        settings.app.version,
        settings.environment,
    )

    try:
        yield
    finally:
        log.info("Отключение от RabbitMQ")
        await broker.stop()
        await db.close_db_pool(app.state.db_pool)
        log.info("Приложение остановлено")


def create_app() -> FastAPI:
    """Собрать и настроить приложение FastAPI."""
    settings = config.get_settings()

    # Инициализация OTel (ДО создания app, чтобы инструментация подхватилась)
    try:
        setup_tracing()
    except Exception as e:  # noqa: BLE001
        log.warning("OTel tracing disabled", error=str(e))

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        description=settings.app.description,
        lifespan=lifespan,
    )

    # Авто-инструментация
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    AsyncPGInstrumentor().instrument()

    @app.middleware("http")
    async def log_requests(request: Request, call_next):  # noqa: ANN001, ANN202
        request_id = uuid.uuid4().hex[:8]
        # Привязываем request_id к контексту structlog
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            log.info("Request started", method=request.method, path=request.url.path)
            response = await call_next(request)
            log.info("Request finished", status_code=response.status_code)
            return response
        finally:
            # Чистим контекст после запроса
            structlog.contextvars.clear_contextvars()

    app.include_router(api_router)
    return app


app = create_app()

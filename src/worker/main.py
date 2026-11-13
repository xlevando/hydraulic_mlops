"""FastStream worker: inference ML-моделей из очереди RabbitMQ."""

import asyncio
import json
import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor

import asyncpg
import pandas as pd
import structlog
from aiohttp import web
from faststream import FastStream
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from src.broker import DLQ_QUEUE, DLX, TASKS_QUEUE, WORKER_CONCURRENCY, broker
from src.db import close_db_pool, create_db_pool
from src.logging_config import setup_logging
from src.services.model_registry import load_champion_models
from src.tracing import setup_tracing

log = structlog.get_logger()
tracer = trace.get_tracer(__name__)

# метрики prometheus
TASKS_PROCESSED = Counter(
    "worker_tasks_processed_total",
    "Total processed tasks",
    ["status"],
)
INFERENCE_DURATION = Histogram(
    "worker_inference_duration_seconds",
    "Inference duration",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
)
TASKS_IN_PROGRESS = Gauge(
    "worker_tasks_in_progress",
    "Tasks currently in progress",
)

_MODELS: dict = {}
_EXECUTOR = ThreadPoolExecutor(max_workers=WORKER_CONCURRENCY)
_DB_POOL: asyncpg.Pool | None = None
_INFLIGHT_TASKS: set[asyncio.Task] = set()
_SHUTDOWN_EVENT = asyncio.Event()
_HEALTH_RUNNER: web.AppRunner | None = None

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_results (
    task_id VARCHAR(32) PRIMARY KEY,
    predictions JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
"""

_SAVE_RESULT_SQL = """
INSERT INTO task_results (task_id, predictions)
VALUES ($1, $2)
ON CONFLICT (task_id) DO NOTHING
"""


def _get_inference_delay() -> float:
    """Длительность inference (для экспериментов)."""
    return float(os.getenv("INFERENCE_DELAY_SEC", "0.5"))


def _run_inference(features: dict[str, float]) -> dict[str, int]:
    """Синхронный inference (в пуле потоков)."""
    time.sleep(_get_inference_delay())

    reference_model = next(iter(_MODELS.values()))
    expected_features = list(reference_model.feature_names_in_)

    X = pd.DataFrame(  # noqa: N806
        [[features[f] for f in expected_features]],
        columns=expected_features,
    )

    return {target: int(model.predict(X)[0]) for target, model in _MODELS.items()}


async def _save_result(task_id: str, predictions: dict[str, int]) -> None:
    """Сохранить результат в БД (идемпотентно)."""
    if _DB_POOL is None:
        log.warning("DB pool not initialized, skipping save")
        return
    try:
        async with _DB_POOL.acquire() as conn:
            await conn.execute(_SAVE_RESULT_SQL, task_id, json.dumps(predictions))
        log.info("Result saved to DB")  # task_id подтянется сам
    except Exception as e:
        # Логируем ошибку со стектрейсом (exc_info=True)
        log.error("Failed to save result to DB", error=str(e), exc_info=True)
        raise


@broker.subscriber(TASKS_QUEUE)
async def process_task(payload: dict) -> None:
    """Обработать задачу из очереди."""
    task_id = payload.get("task_id", "unknown")
    features = payload.get("features", {})

    # Middleware уже извлёк контекст из заголовков сообщения и создал спан process
    # Здесь tracer.start_as_current_span создаст дочерний спан
    with tracer.start_as_current_span("process_task") as span:
        span.set_attribute("task.id", task_id)
        structlog.contextvars.bind_contextvars(task_id=task_id)

        TASKS_IN_PROGRESS.inc()

        current = asyncio.current_task()
        if current is not None:
            _INFLIGHT_TASKS.add(current)

        try:
            log.info("Processing task started")
            loop = asyncio.get_event_loop()

            with tracer.start_as_current_span("inference"):
                start_time = time.time()
                predictions = await loop.run_in_executor(_EXECUTOR, _run_inference, features)
                INFERENCE_DURATION.observe(time.time() - start_time)

            log.info("Task inference done", predictions=predictions)

            with tracer.start_as_current_span("save_to_db"):
                await _save_result(task_id, predictions)

            TASKS_PROCESSED.labels(status="ok").inc()

        except Exception as e:
            TASKS_PROCESSED.labels(status="error").inc()
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            log.error("Failed to process task", error=str(e), exc_info=True)

            # Принудительно отправляем спаны в Collector
            trace.get_tracer_provider().force_flush(timeout_millis=3000)

            raise e

        finally:
            TASKS_IN_PROGRESS.dec()
            structlog.contextvars.clear_contextvars()
            if current is not None:
                _INFLIGHT_TASKS.discard(current)


@broker.subscriber(DLQ_QUEUE, DLX)
async def dead_letter_handler(payload: dict) -> None:
    """Принимаем сообщения из DLQ: логируем и подтверждаем.

    Это создаёт binding dlx => tasks.dlq и гарантирует, что dead-letter
    сообщения не дропаются в никуда.
    """
    log.error("DLQ received (unrecoverable)", payload=payload)


async def _health_handler(request: web.Request) -> web.Response:
    """Health-check: отвечает, даже если воркер занят inference."""
    return web.json_response(
        {
            "status": "ok",
            "models": len(_MODELS),
            "inflight_tasks": len(_INFLIGHT_TASKS),
            "shutting_down": _SHUTDOWN_EVENT.is_set(),
        }
    )


async def _start_health_server(port: int = 8001) -> web.AppRunner:
    """Запустить health-check HTTP-сервер."""
    app = web.Application()
    app.router.add_get("/healthz", _health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("Health server on :%d", port)
    return runner


# Graceful shutdown
def _install_sigterm_handler(loop: asyncio.AbstractEventLoop) -> None:
    """Обработчик SIGTERM."""

    def _handler() -> None:
        log.info("SIGTERM received, starting graceful shutdown")
        _SHUTDOWN_EVENT.set()

    loop.add_signal_handler(signal.SIGTERM, _handler)


app = FastStream(broker)


@app.after_startup
async def startup() -> None:
    """Загрузить модели + БД + health-сервер."""
    global _DB_POOL, _MODELS, _HEALTH_RUNNER
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    try:
        setup_tracing(service_name="hydraulic-worker")
    except Exception as e:  # noqa: BLE001
        log.warning("OTel tracing disabled", error=str(e))

    log.info("Инициализация БД")
    _DB_POOL = await create_db_pool()
    async with _DB_POOL.acquire() as conn:
        await conn.execute(_CREATE_TABLE_SQL)

    log.info("Загрузка champion-моделей из MLflow")
    _MODELS = load_champion_models()
    log.info("Загружено моделей: %d", len(_MODELS))

    _HEALTH_RUNNER = await _start_health_server(port=8001)

    # Запускаем сервер метрик Prometheus на порту 8002
    start_http_server(8002)
    log.info("Prometheus metrics server on :8002")

    # SIGTERM
    _install_sigterm_handler(asyncio.get_event_loop())


@app.on_shutdown
async def shutdown() -> None:
    """Graceful shutdown."""
    global _HEALTH_RUNNER
    log.info("Graceful shutdown: ждём %d inflight-задач", len(_INFLIGHT_TASKS))

    # Ждём завершения текущих задач (с таймаутом)
    if _INFLIGHT_TASKS:
        done, pending = await asyncio.wait(_INFLIGHT_TASKS, timeout=30.0)  # noqa: RUF059
        if pending:
            log.warning("Timeout: %d tasks still running", len(pending))
        else:
            log.info("All inflight tasks completed")

    if _HEALTH_RUNNER is not None:
        await _HEALTH_RUNNER.cleanup()
        _HEALTH_RUNNER = None

    _EXECUTOR.shutdown(wait=True)

    # Закрываем БД
    if _DB_POOL is not None:
        await close_db_pool(_DB_POOL)

    log.info("Graceful shutdown complete")


if __name__ == "__main__":
    setup_tracing()
    asyncio.run(app.run())

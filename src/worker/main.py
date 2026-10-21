"""FastStream worker: inference ML-моделей из очереди RabbitMQ."""

import asyncio
import json
import logging
import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor

import asyncpg
import pandas as pd
from aiohttp import web
from faststream import FastStream

from src.broker import DLQ_QUEUE, DLX, TASKS_QUEUE, WORKER_CONCURRENCY, broker
from src.db import close_db_pool, create_db_pool
from src.logging_config import setup_logging
from src.services.model_registry import load_champion_models

log = logging.getLogger(__name__)

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
        log.info("Result saved for task %s", task_id)
    except Exception as e:
        log.error("Failed to save result for %s: %s", task_id, e)
        raise


@broker.subscriber(TASKS_QUEUE)
async def process_task(payload: dict) -> None:
    """Обработать задачу из очереди."""
    task_id = payload.get("task_id", "unknown")
    features = payload.get("features", {})

    # Регистрируем inflight-задачу
    current = asyncio.current_task()
    if current is not None:
        _INFLIGHT_TASKS.add(current)

    try:
        log.info("Processing task %s", task_id)
        loop = asyncio.get_event_loop()
        predictions = await loop.run_in_executor(_EXECUTOR, _run_inference, features)
        log.info("Task %s done: %s", task_id, predictions)
        await _save_result(task_id, predictions)
    finally:
        if current is not None:
            _INFLIGHT_TASKS.discard(current)


@broker.subscriber(DLQ_QUEUE, DLX)
async def dead_letter_handler(payload: dict) -> None:
    """Принимаем сообщения из DLQ: логируем и подтверждаем.

    Это создаёт binding dlx => tasks.dlq и гарантирует, что dead-letter
    сообщения не дропаются в никуда.
    """
    log.error("DLQ received (unrecoverable): %s", payload)


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

    log.info("Инициализация БД")
    _DB_POOL = await create_db_pool()
    async with _DB_POOL.acquire() as conn:
        await conn.execute(_CREATE_TABLE_SQL)

    log.info("Загрузка champion-моделей из MLflow")
    _MODELS = load_champion_models()
    log.info("Загружено моделей: %d", len(_MODELS))

    _HEALTH_RUNNER = await _start_health_server(port=8001)

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
    asyncio.run(app.run())

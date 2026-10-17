"""FastStream worker: inference ML-моделей из очереди RabbitMQ."""

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import asyncpg
import pandas as pd
from faststream import FastStream

from src.broker import TASKS_QUEUE, broker
from src.db import close_db_pool, create_db_pool
from src.logging_config import setup_logging
from src.services.model_registry import load_champion_models

log = logging.getLogger(__name__)


_MODELS: dict = {}
_EXECUTOR = ThreadPoolExecutor(max_workers=4)
_DB_POOL: asyncpg.Pool | None = None

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

    log.info("Processing task %s", task_id)

    loop = asyncio.get_event_loop()
    predictions = await loop.run_in_executor(
        _EXECUTOR,
        _run_inference,
        features,
    )

    log.info("Task %s done: %s", task_id, predictions)

    await _save_result(task_id, predictions)


app = FastStream(broker)


@app.after_startup
async def startup() -> None:
    """Загрузить модели + инициализировать БД при старте."""
    global _DB_POOL
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    log.info("Инициализация БД")
    _DB_POOL = await create_db_pool()
    async with _DB_POOL.acquire() as conn:
        await conn.execute(_CREATE_TABLE_SQL)

    log.info("Загрузка champion-моделей из MLflow")

    global _MODELS
    _MODELS = load_champion_models()

    log.info("Загружено моделей: %d", len(_MODELS))


@app.on_shutdown
async def shutdown() -> None:
    """Graceful shutdown: дождаться текущих задач + закрыть пул."""
    log.info("Graceful shutdown: завершаем текущие задачи...")
    _EXECUTOR.shutdown(wait=True)
    if _DB_POOL is not None:
        await close_db_pool(_DB_POOL)
    log.info("Graceful shutdown complete")


if __name__ == "__main__":
    asyncio.run(app.run())

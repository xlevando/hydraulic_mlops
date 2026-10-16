"""FastStream worker: inference ML-моделей из очереди RabbitMQ."""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from faststream import FastStream

from src.broker import TASKS_QUEUE, broker
from src.logging_config import setup_logging
from src.services.model_registry import load_champion_models

log = logging.getLogger(__name__)


_MODELS: dict = {}
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


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


app = FastStream(broker)


@app.after_startup
async def startup() -> None:
    """Загрузить модели при старте воркера."""
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))
    log.info("Загрузка champion-моделей из MLflow")

    global _MODELS
    _MODELS = load_champion_models()

    log.info("Загружено моделей: %d", len(_MODELS))


if __name__ == "__main__":
    asyncio.run(app.run())

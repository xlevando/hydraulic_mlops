"""Загрузка моделей из MLflow Model Registry."""

import logging
import os

import mlflow
import mlflow.sklearn
from mlflow import MlflowClient

log = logging.getLogger(__name__)


MODEL_NAMES = {
    "cooler": "hydraulic_cooler",
    "valve": "hydraulic_valve",
    "pump": "hydraulic_pump",
    "accumulator": "hydraulic_accumulator",
}


def get_tracking_uri() -> str:
    """Получить URI MLflow Tracking Server из окружения."""
    return os.getenv(
        "MLFLOW_TRACKING_URI",
        "http://localhost:5001",
    )


def load_champion_models() -> dict[str, object]:
    """Загрузить champion-модели из MLflow Registry.

    Модели загружаются один раз при старте приложения.
    """
    tracking_uri = get_tracking_uri()

    mlflow.set_tracking_uri(tracking_uri)

    client = MlflowClient(
        tracking_uri=tracking_uri,
    )

    models: dict[str, object] = {}

    for target, model_name in MODEL_NAMES.items():
        model_uri = f"models:/{model_name}@champion"

        version = client.get_model_version_by_alias(
            model_name,
            "champion",
        )

        log.info(
            "Загрузка модели: %s → v%s (alias=champion, run=%s)",
            model_name,
            version.version,
            version.run_id,
        )

        models[target] = mlflow.sklearn.load_model(model_uri)

        log.info(
            "Модель загружена: %s → v%s",
            model_name,
            version.version,
        )

    return models

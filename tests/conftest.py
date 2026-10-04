"""Общие фикстуры тестов."""

import os
from unittest.mock import MagicMock

# Тесты должны быть детерминированными: окружение предполагает, что
# Postgres НЕдоступен. Настраиваем до импорта src.app — Settings читает
# переменные окружения при создании приложения.
os.environ["DATABASE__URL"] = "postgresql://postgres:postgres@127.0.0.1:59999/hydraulic_mlops"
os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5001"

from collections.abc import AsyncGenerator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from src.app import app

# 170 признаков
_FEATURES = [
    f"{s}_{st}"
    for s in [
        "PS1",
        "PS2",
        "PS3",
        "PS4",
        "PS5",
        "PS6",
        "EPS1",
        "FS1",
        "FS2",
        "TS1",
        "TS2",
        "TS3",
        "TS4",
        "VS1",
        "CE",
        "CP",
        "SE",
    ]
    for st in ["mean", "std", "rms", "min", "max", "median", "skew", "kurtosis", "delta", "slope"]
]


def _mock_model():
    m = MagicMock()
    m.feature_names_in_ = _FEATURES
    m.predict.return_value = [1]
    return m


import src.services.model_registry as model_registry  # noqa: E402

model_registry.load_champion_models = lambda: {
    "cooler": _mock_model(),
    "valve": _mock_model(),
    "pump": _mock_model(),
    "accumulator": _mock_model(),
}


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """HTTP-клиент приложения: запускает lifespan (пул БД, app.state)."""
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http

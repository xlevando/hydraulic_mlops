"""Общие фикстуры тестов."""

import os
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

# Переменные окружения ДО любых импортов src.*
os.environ["DATABASE__URL"] = "postgresql://postgres:postgres@127.0.0.1:59999/hydraulic_mlops"
os.environ["MLFLOW_TRACKING_URI"] = "http://localhost:5001"

# Мок модели — до импорта src.services
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


def _mock_model() -> MagicMock:
    m = MagicMock()
    m.feature_names_in_ = _FEATURES
    m.predict.return_value = [1]
    return m


_MOCK_MODELS = {
    "cooler": _mock_model(),
    "valve": _mock_model(),
    "pump": _mock_model(),
    "accumulator": _mock_model(),
}

# Патчим функцию в model_registry ДО импорта src.app
from src.services import model_registry  # noqa: E402

model_registry.load_champion_models = lambda: _MOCK_MODELS

# Импорты после патча
import pytest  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from faststream.rabbit import TestRabbitBroker  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from src.app import app  # noqa: E402
from src.broker import broker  # noqa: E402


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """HTTP-клиент приложения: подменяет RabbitMQ на in-memory и запускает lifespan."""
    async with TestRabbitBroker(broker):
        async with LifespanManager(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as http:
                yield http

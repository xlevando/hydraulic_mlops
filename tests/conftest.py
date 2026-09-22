"""Общие фикстуры тестов."""

import os

# Тесты должны быть детерминированными: окружение предполагает, что
# Postgres НЕдоступен. Настраиваем до импорта src.app — Settings читает
# переменные окружения при создании приложения.
os.environ["DATABASE__URL"] = "postgresql://postgres:postgres@127.0.0.1:59999/hydraulic_mlops"

from collections.abc import AsyncGenerator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from src.app import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """HTTP-клиент приложения: запускает lifespan (пул БД, app.state)."""
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http

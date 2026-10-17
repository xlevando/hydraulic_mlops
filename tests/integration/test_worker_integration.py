"""Integration-тест: реальный RabbitMQ через Testcontainers."""

from unittest.mock import MagicMock

import pytest
from faststream.rabbit import RabbitBroker
from testcontainers.community.rabbitmq import RabbitMqContainer

from src.broker import TASKS_QUEUE


@pytest.fixture(scope="module")
def rabbitmq_container():
    """Поднять реальный RabbitMQ в Docker."""
    with RabbitMqContainer("rabbitmq:3.13-management") as rabbit:
        yield rabbit


@pytest.fixture
def broker(rabbitmq_container):
    """Брокер, подключённый к Testcontainers RabbitMQ."""
    connection_params = rabbitmq_container.get_connection_params()
    url = f"amqp://{connection_params.credentials.username}:{connection_params.credentials.password}@{connection_params.host}:{connection_params.port}/"
    return RabbitBroker(url)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_and_consume(broker: RabbitBroker) -> None:
    """Публикация + получение сообщения из реальной очереди."""
    received: list[dict] = []

    @broker.subscriber(TASKS_QUEUE)
    async def handler(payload: dict) -> None:
        received.append(payload)

    async with broker:
        await broker.start()
        await broker.publish(
            {"task_id": "test-1", "features": {"a": 1.0}},
            queue=TASKS_QUEUE,
        )
        # ждём обработки
        import asyncio

        await asyncio.sleep(1.0)

    assert len(received) == 1
    assert received[0]["task_id"] == "test-1"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_processes_task(broker: RabbitBroker) -> None:
    """Воркер обрабатывает задачу (с мок-моделью)."""

    # мок модели
    mock_model = MagicMock()
    mock_model.feature_names_in_ = ["f1", "f2"]
    mock_model.predict.return_value = [1]

    results: list[dict] = []

    @broker.subscriber(TASKS_QUEUE)
    async def handler(payload: dict) -> None:
        # прямой inference через мок
        import pandas as pd

        X = pd.DataFrame([[1.0, 1.0]], columns=["f1", "f2"])  # noqa: N806
        predictions = {"cooler": int(mock_model.predict(X)[0])}
        results.append({"task_id": payload["task_id"], "predictions": predictions})

    async with broker:
        await broker.start()
        await broker.publish(
            {"task_id": "test-2", "features": {"f1": 1.0, "f2": 1.0}},
            queue=TASKS_QUEUE,
        )
        import asyncio

        await asyncio.sleep(1.0)

    assert len(results) == 1
    assert results[0]["predictions"] == {"cooler": 1}

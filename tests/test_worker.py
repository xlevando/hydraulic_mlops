"""Unit-тесты /api/v1/tasks (публикация в очередь)."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_task_accepted_when_valid(client: AsyncClient) -> None:
    """POST /tasks — 202 при валидных признаках."""
    from src.app import app

    assert app.state.models, "Models not loaded — check conftest mock"

    mock_model = next(iter(app.state.models.values()))
    features = {f: 1.0 for f in mock_model.feature_names_in_}

    # Мокаем publish (не нужен реальный RabbitMQ)
    with patch("src.api.tasks.broker.publish", new=AsyncMock()):
        response = await client.post(
            "/api/v1/tasks",
            json={"features": features},
        )

    assert response.status_code == 202, response.text
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "accepted"


@pytest.mark.asyncio
async def test_task_rejected_when_missing_features(client: AsyncClient) -> None:
    """POST /tasks — 422 при отсутствии признаков."""
    from src.app import app

    mock_model = next(iter(app.state.models.values()))
    features = {f: 1.0 for f in mock_model.feature_names_in_[:-5]}

    response = await client.post(
        "/api/v1/tasks",
        json={"features": features},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "missing_features" in detail

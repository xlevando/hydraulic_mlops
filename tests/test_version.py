"""Тесты /api/v1/version."""

from httpx import AsyncClient


async def test_version_returns_version(client: AsyncClient) -> None:
    """GET /api/v1/version возвращает версию и окружение."""
    response = await client.get("/api/v1/version")

    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "environment" in data
    assert data["version"] != ""

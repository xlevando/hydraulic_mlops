"""Тесты health-эндпоинтов."""

from httpx import AsyncClient


async def test_healthz_returns_ok(client: AsyncClient) -> None:
    """GET /healthz отвечает 200 и {"status": "ok"} без обращения к БД."""
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_report_degraded_when_postgres_unavailable(
    client: AsyncClient,
) -> None:
    """GET /api/v1/health отдаёт 503 и деградацию, если Postgres недоступен."""
    response = await client.get("/api/v1/health")

    assert response.status_code == 503

    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["postgres"]["status"] == "unavailable"
    assert body["dependencies"]["application"]["status"] == "healthy"
    assert "hydraulic-mlops" in body["dependencies"]["application"]["detail"]

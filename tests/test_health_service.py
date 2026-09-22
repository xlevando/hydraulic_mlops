"""Unit-тесты логики health-отчёта."""

from src.config import AppSettings, Settings
from src.schemas import HealthStatus, ReportStatus
from src.services import health as health_service


class _DeadPool:
    """Пул-заглушка: любой запрос падает, как будто Postgres недоступен."""

    async def fetchval(self, query: str) -> object:
        raise OSError("connection refused")


class _HealthyPool:
    """Пул-заглушка: возвращает версию Postgres."""

    async def fetchval(self, query: str) -> str:
        return "PostgreSQL 16.4, compiled by clang, 64-bit"


def test_check_application_healthy() -> None:
    """Проверка приложения всегда healthy и несёт версию в detail."""
    settings = Settings(app=AppSettings(name="hydraulic-mlops", version="9.9.9"))
    dependency = health_service.check_application(settings)

    assert dependency.status is HealthStatus.healthy
    assert "9.9.9" in (dependency.detail or "")


async def test_check_postgres_unavailable_on_error() -> None:
    """Падение запроса фиксируется как unavailable с текстом ошибки."""
    dependency = await health_service.check_postgres(_DeadPool())

    assert dependency.status is HealthStatus.unavailable
    assert "OSError" in (dependency.detail or "")


async def test_check_postgres_healthy() -> None:
    """Успешный запрос фиксируется как healthy с версией БД."""
    dependency = await health_service.check_postgres(_HealthyPool())

    assert dependency.status is HealthStatus.healthy
    assert "PostgreSQL 16.4" in (dependency.version or "")


async def test_build_report_degraded_when_dependency_down() -> None:
    """Нездоровая зависимость роняет общий статус до degraded."""
    settings = Settings(app=AppSettings(name="hydraulic-mlops"))
    report = await health_service.build_report(_DeadPool(), settings)

    assert report.status is ReportStatus.degraded
    assert report.dependencies["application"].status is HealthStatus.healthy
    assert report.dependencies["postgres"].status is HealthStatus.unavailable

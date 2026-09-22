"""Pydantic-контракты API приложения."""

from enum import StrEnum

from pydantic import BaseModel, Field

# === /healthz ===


class HealthzResponse(BaseModel):
    """Ответ быстрой проверки /healthz."""

    status: str = "ok"


# === /api/v1/version ===


class VersionResponse(BaseModel):
    """Ответ /api/v1/version — версия приложения"""

    version: str = Field(..., description="Версия приложения")
    environment: str = Field(..., description="Окружение")


# === /api/v1/health (E2E) ===


class HealthStatus(StrEnum):
    """Статус отдельной зависимости"""

    healthy = "healthy"
    unavailable = "unavailable"


class ReportStatus(StrEnum):
    """Общий статус приложения в health-отчёте."""

    ok = "ok"
    degraded = "degraded"


class DependencyHealth(BaseModel):
    """Здоровье одной зависимости: статус, время ответа и деталь."""

    status: HealthStatus
    response_time_ms: float = Field(..., description="Время ответа в мс")
    version: str | None = Field(None, description="Версия зависимости")
    detail: str | None = Field(None, description="Человекочитаемая деталь")


class HealthReport(BaseModel):
    """Сводный health-отчёт: общий статус, зависимости и общее время."""

    status: ReportStatus
    dependencies: dict[str, DependencyHealth]
    total_response_time_ms: float = Field(..., description="Общее время ответа в мс")

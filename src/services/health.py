"""Логика health-отчёта: проверка зависимостей и сводка.

Две зависимости — само приложение и Postgres. Каждая проверка возвращает
`DependencyHealth`; `build_report` складывает их в `HealthReport` и выводит
общий статус. Появится новая зависимость (S3, Redis) — добавляется ещё одна
проверка и строка в словарь, контракт ответа не меняется.
"""

import logging
import time

from asyncpg import Pool, PostgresError

from src.config import Settings
from src.schemas import DependencyHealth, HealthReport, HealthStatus, ReportStatus

log = logging.getLogger(__name__)


def check_application(settings: Settings) -> DependencyHealth:
    """Проверить само приложение: конфигурация доступна."""
    start = time.perf_counter()

    detail = f"{settings.app.name} {settings.app.version} ({settings.environment})"

    elapsed_ms = (time.perf_counter() - start) * 1000
    return DependencyHealth(
        status=HealthStatus.healthy,
        response_time_ms=round(elapsed_ms, 2),
        detail=detail,
    )


async def check_postgres(pool: Pool) -> DependencyHealth:
    """Проверить Postgres: выполнить запрос и прочитать версию.

    Падение (нет коннекта, нет базы, таймаут) — не ошибка health-эндпоинта,
    а статус `unavailable` с текстом ошибки для дежурного.
    """
    start = time.perf_counter()

    try:
        version = await pool.fetchval("SELECT version()")

    except (OSError, PostgresError, TimeoutError) as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        detail = f"{type(exc).__name__}: {exc}"
        log.warning("postgres_health_check_failed: %s", detail)

        return DependencyHealth(
            status=HealthStatus.unavailable,
            response_time_ms=round(elapsed_ms, 2),
            detail=detail,
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    return DependencyHealth(
        status=HealthStatus.healthy,
        response_time_ms=round(elapsed_ms, 2),
        version=str(version).split(",")[0],
    )


async def build_report(pool: Pool, settings: Settings) -> HealthReport:
    """Собрать health-отчёт по приложению и Postgres."""
    start = time.perf_counter()

    dependencies = {
        "application": check_application(settings),
        "postgres": await check_postgres(pool),
    }

    healthy = all(dep.status is HealthStatus.healthy for dep in dependencies.values())

    elapsed_ms = (time.perf_counter() - start) * 1000
    return HealthReport(
        status=ReportStatus.ok if healthy else ReportStatus.degraded,
        dependencies=dependencies,
        total_response_time_ms=round(elapsed_ms, 2),
    )

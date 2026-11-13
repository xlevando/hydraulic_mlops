"""Настройка структурированного (JSON) логирования."""

import logging
import sys

import structlog
from opentelemetry import trace


def add_otel_trace_id(logger, method_name, event_dict):  # noqa: ANN001, ANN201
    """Добавляет trace_id и span_id в лог, если есть активный спан."""
    span = trace.get_current_span()
    if span.is_recording():
        ctx = span.get_span_context()
        # Форматируем в hex (как в Jaeger)
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def setup_logging(level: str = "INFO") -> None:
    """Настроить JSON-логи в stdout для всего приложения."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Настраиваем стандартный logging (чтобы uvicorn и FastStream не ломали JSON)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Отключаем лишние хендлеры uvicorn, чтобы они не дублировали логи в старом формате
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    # Настраиваем structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # Автоматически добавляет task_id/request_id
            add_otel_trace_id,
            structlog.processors.add_log_level,  # level: "info"
            structlog.processors.TimeStamper(fmt="iso", utc=True),  # timestamp: "2026-11-12T..."
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,  # Красиво выводит исключения
            structlog.processors.JSONRenderer(),  # Вывод в JSON
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

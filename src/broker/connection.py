"""Подключение к RabbitMQ."""

import os

from faststream.rabbit import Channel, RabbitBroker
from faststream.rabbit.opentelemetry import RabbitTelemetryMiddleware

# Параллелизм воркера задаётся ThreadPoolExecutor(max_workers=WORKER_CONCURRENCY)
# в src/worker/main.py. prefetch_count == WORKER_CONCURRENCY:
#   - ровно столько сообщений брокер отдаёт воркеру "в работу" (unacked);
#   - больше - сообщения лежат unacked в памяти воркера без пользы
#     (in-memory буфер), задерживая ack;
#   - меньше - часть потоков пула простаивает.
# для RabbitMQ нужен именно RabbitTelemetryMiddleware

WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "4"))

from opentelemetry import trace  # noqa: E402

# Получаем TracerProvider, который уже был установлен глобально через setup_tracing()
tracer_provider = trace.get_tracer_provider()

broker = RabbitBroker(
    os.getenv("RABBITMQ_URL", "amqp://admin:admin@localhost:5672/"),
    default_channel=Channel(
        prefetch_count=WORKER_CONCURRENCY,
        publisher_confirms=True,
    ),
    middlewares=[RabbitTelemetryMiddleware(tracer_provider=tracer_provider)],
)

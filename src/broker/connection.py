"""Подключение к RabbitMQ."""

import os

from faststream.rabbit import Channel, RabbitBroker

# Параллелизм воркера задаётся ThreadPoolExecutor(max_workers=WORKER_CONCURRENCY)
# в src/worker/main.py. prefetch_count == WORKER_CONCURRENCY:
#   - ровно столько сообщений брокер отдаёт воркеру "в работу" (unacked);
#   - больше - сообщения лежат unacked в памяти воркера без пользы
#     (in-memory буфер), задерживая ack;
#   - меньше - часть потоков пула простаивает.
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "4"))

broker = RabbitBroker(
    os.getenv("RABBITMQ_URL", "amqp://admin:admin@localhost:5672/"),
    default_channel=Channel(
        prefetch_count=WORKER_CONCURRENCY,
        publisher_confirms=True,
    ),
)

"""Пакет для работы с RabbitMQ."""

from src.broker.connection import WORKER_CONCURRENCY, broker
from src.broker.queues import DLQ_QUEUE, DLX, TASKS_QUEUE

__all__ = [
    "DLQ_QUEUE",
    "DLX",
    "TASKS_QUEUE",
    "WORKER_CONCURRENCY",
    "broker",
]

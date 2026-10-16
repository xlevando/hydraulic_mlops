"""Пакет для работы с RabbitMQ."""

from src.broker.connection import broker
from src.broker.queues import DLQ_QUEUE, TASKS_QUEUE

__all__ = ["DLQ_QUEUE", "TASKS_QUEUE", "broker"]

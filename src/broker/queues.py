"""Очереди RabbitMQ с backpressure и DLQ.

Основная очередь (`tasks`) имеет ограничение ёмкости (QUEUE_MAX_LENGTH).
Когда очередь переполняется, RabbitMQ отклоняет публикацию новых
сообщений (`reject-publish`) - механизм backpressure:
издатель вынужден замедлиться.

Сообщения, которые не удалось обработать после N попыток,
автоматически попадают в `tasks.dlq` (Dead Letter Queue) через
exchange `dlx`.
"""

import os

from faststream.rabbit import ExchangeType, RabbitExchange, RabbitQueue

QUEUE_MAX_LENGTH = int(os.getenv("QUEUE_MAX_LENGTH", "10000"))

DLX = RabbitExchange(
    name="dlx",
    type=ExchangeType.DIRECT,
    durable=True,
)

TASKS_QUEUE = RabbitQueue(
    name="tasks",
    durable=True,
    routing_key="tasks",
    arguments={
        "x-max-length": QUEUE_MAX_LENGTH,
        "x-overflow": "reject-publish",
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "tasks.dlq",
    },
)

DLQ_QUEUE = RabbitQueue(
    name="tasks.dlq",
    durable=True,
    routing_key="tasks.dlq",
)

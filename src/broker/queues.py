"""Очереди RabbitMQ с backpressure и DLQ.

Основная очередь (`tasks`) имеет ограничение в 10 000 сообщений.
Когда очередь переполняется, RabbitMQ отклоняет публикацию новых
сообщений (`reject-publish`) - механизм backpressure:
издатель вынужден замедлиться.

Сообщения, которые не удалось обработать после N попыток,
автоматически попадают в `tasks.dlq` (Dead Letter Queue) через
exchange `dlx`.
"""

from faststream.rabbit import RabbitQueue

TASKS_QUEUE = RabbitQueue(
    name="tasks",
    durable=True,
    arguments={
        "x-max-length": 10000,
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

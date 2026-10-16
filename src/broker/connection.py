"""Подключение к RabbitMQ."""

import os

from faststream.rabbit import RabbitBroker

broker = RabbitBroker(
    os.getenv("RABBITMQ_URL", "amqp://admin:admin@localhost:5672/"),
)

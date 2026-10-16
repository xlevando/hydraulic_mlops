"""Подключение к RabbitMQ."""

import os

from faststream.rabbit import Channel, RabbitBroker

broker = RabbitBroker(
    os.getenv("RABBITMQ_URL", "amqp://admin:admin@localhost:5672/"),
    default_channel=Channel(prefetch_count=10),  # backpressure
)

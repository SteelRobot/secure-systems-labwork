"""Публикация сообщений в RabbitMQ (обменник app.events, ключ = имя очереди)."""
import json

import pika

from . import config


def publish(queue: str, message: dict) -> None:
    """queue: audit | notifications | reports. Сообщения – persistent."""
    params = pika.ConnectionParameters(
        host=config.BROKER_HOST,
        credentials=pika.PlainCredentials(config.BROKER_USER, config.BROKER_PASSWORD),
    )
    with pika.BlockingConnection(params) as conn:
        ch = conn.channel()
        ch.confirm_delivery()
        ch.basic_publish(
            exchange="app.events", routing_key=queue,
            body=json.dumps(message, default=str).encode(),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )

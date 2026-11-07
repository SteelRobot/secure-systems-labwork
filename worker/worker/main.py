"""Фоновый обработчик очередей RabbitMQ: audit, notifications, reports.
Сейчас – каркас: сообщение принимается, логируется и подтверждается (ack).
Реальная логика добавляется в handlers по мере реализации эндпоинтов."""
import json
import logging
import os
import time

import pika

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")


def handle_audit(msg: dict) -> None:
    log.info("audit: %s", msg)  # TODO: INSERT INTO audit_log


def handle_notifications(msg: dict) -> None:
    log.info("notification: %s", msg)  # TODO: письмо в Mailpit (SMTP mail:1025)


def handle_reports(msg: dict) -> None:
    # TODO: сформировать CSV/XLSX -> хранилище, затем POST ссылки в external-stubs /finance/reports
    log.info("report: %s", msg)


HANDLERS = {"audit": handle_audit, "notifications": handle_notifications,
            "reports": handle_reports}


def make_callback(handler):
    def callback(ch, method, properties, body):
        try:
            handler(json.loads(body))
            ch.basic_ack(method.delivery_tag)
        except Exception:
            log.exception("handler failed")
            # без requeue: после x-delivery-limit сообщение уйдёт в <queue>.dlq
            ch.basic_nack(method.delivery_tag, requeue=True)
    return callback


def main() -> None:
    params = pika.ConnectionParameters(
        host=os.environ["BROKER_HOST"],
        credentials=pika.PlainCredentials(os.environ["BROKER_USER"], os.environ["BROKER_PASSWORD"]),
        heartbeat=30,
    )
    while True:
        try:
            conn = pika.BlockingConnection(params)
            break
        except pika.exceptions.AMQPConnectionError:
            log.warning("broker недоступен, повтор через 3 с")
            time.sleep(3)
    ch = conn.channel()
    ch.basic_qos(prefetch_count=10)
    for name, handler in HANDLERS.items():
        ch.basic_consume(queue=name, on_message_callback=make_callback(handler))
    log.info("worker запущен, очереди: %s", ", ".join(HANDLERS))
    ch.start_consuming()


if __name__ == "__main__":
    main()

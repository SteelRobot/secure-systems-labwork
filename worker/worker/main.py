"""Фоновый обработчик очередей RabbitMQ: audit, notifications, reports.
Записывает события аудита в базу данных PostgreSQL (под ролью app_worker)."""
import json
import logging
import os
import time
import pika
import psycopg

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")

DB_CONNINFO = f"host={os.environ['DB_HOST']} dbname={os.environ['DB_NAME']} user={os.environ['DB_USER']} password={os.environ['DB_PASSWORD']}"

def handle_audit(msg: dict) -> None:
    log.info("audit event received: %s", msg)
    actor_id = msg.get("actor_user_id")
    action = msg.get("action")
    entity_type = msg.get("entity_type")
    entity_id = msg.get("entity_id")
    details = msg.get("details", {})
    ip = msg.get("ip_address")

    if not action or not entity_type:
        log.warning("skipped invalid audit msg: %s", msg)
        return

    with psycopg.connect(DB_CONNINFO) as conn:
        conn.execute(
            """INSERT INTO audit_log (actor_user_id, action, entity_type, entity_id, details, ip_address)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (actor_id, action, entity_type, entity_id, json.dumps(details), ip)
        )
        conn.commit()

def handle_notifications(msg: dict) -> None:
    log.info("notification: %s", msg)

def handle_reports(msg: dict) -> None:
    log.info("report: %s", msg)

HANDLERS = {
    "audit": handle_audit,
    "notifications": handle_notifications,
    "reports": handle_reports
}

def make_callback(handler):
    def callback(ch, method, properties, body):
        try:
            handler(json.loads(body))
            ch.basic_ack(method.delivery_tag)
        except Exception:
            log.exception("handler failed")
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

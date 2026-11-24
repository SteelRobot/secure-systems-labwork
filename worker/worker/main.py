from minio import Minio
import redis
import httpx
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

r = redis.Redis(host=os.environ["REDIS_HOST"], password=os.environ["REDIS_PASSWORD"], decode_responses=True)
storage_client = Minio(os.environ["STORAGE_ENDPOINT"], access_key=os.environ["STORAGE_ACCESS_KEY"], secret_key=os.environ["STORAGE_SECRET_KEY"], secure=False)

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
    log.info("notification event received: %s", msg)
    if msg.get("task") == "send_email":
        to_email = msg.get("to_email")
        subject = msg.get("subject", "Уведомление системы")
        body_text = msg.get("body", "")
        if not to_email:
            return
        
        # Отправка письма через SMTP в Mailpit (локальная заглушка почты)
        import smtplib
        from email.mime.text import MIMEText
        
        smtp_host = os.environ.get("SMTP_HOST", "mail")
        smtp_port = int(os.environ.get("SMTP_PORT", 1025))
        
        try:
            msg_mime = MIMEText(body_text, "plain", "utf-8")
            msg_mime["Subject"] = subject
            msg_mime["From"] = "noreply@univ.local"
            msg_mime["To"] = to_email
            
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.send_message(msg_mime)
            log.info("sent email to %s via %s:%s", to_email, smtp_host, smtp_port)
        except Exception:
            log.exception("failed to send email to %s", to_email)

    elif msg.get("task") == "llm_check":
        check_id = msg.get("check_id")
        app_id = msg.get("application_id")
        if not check_id or not app_id:
            return

        time.sleep(1) # Имитация обработки модели

        issues = [
            "Обратите внимание на соответствие даты загруженных справок текущему учебному семестру"
        ]
        recommendations = [
            "Формально необходимые сведения присутствуют в обращении",
        ]

        with psycopg.connect(DB_CONNINFO) as conn:
            conn.execute(
                """UPDATE llm_checks
                   SET status = 'completed',
                       is_complete = TRUE,
                       issues = %s::jsonb,
                       recommendations = %s::jsonb,
                       completed_at = CURRENT_TIMESTAMP
                   WHERE id = %s""",
                (json.dumps(issues), json.dumps(recommendations), check_id)
            )
            conn.commit()
        log.info("llm check %s completed for application %s", check_id, app_id)


def handle_reports(msg: dict) -> None:
    log.info("report task received: %s", msg)
    if msg.get("task") == "generate_report":
        report_id = msg.get("report_id")
        department_id = msg.get("department_id")
        if not report_id or not department_id:
            return

        # 1. Извлекаем данные по заявкам подразделения из БД
        with psycopg.connect(DB_CONNINFO) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.id, u.full_name, u.university_id, a.support_type, a.academic_year,
                              a.status, a.requested_amount, a.approved_amount, a.created_at, a.submitted_at
                       FROM applications a
                       JOIN users u ON u.id = a.applicant_id
                       WHERE u.department_id = %s AND a.status != 'draft'
                       ORDER BY a.created_at DESC""",
                    (department_id,)
                )
                rows = cur.fetchall()

        # 2. Формируем CSV в памяти
        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID Заявки", "ФИО Заявителя", "Номер", "Тип поддержки", "Учебный год", "Статус", "Запрошено", "Одобрено", "Дата создания"])

        for r_row in rows:
            writer.writerow([
                str(r_row[0]), r_row[1], r_row[2], r_row[3], r_row[4], r_row[5],
                float(r_row[6]) if r_row[6] is not None else "",
                float(r_row[7]) if r_row[7] is not None else "",
                r_row[8].isoformat() if r_row[8] else ""
            ])

        csv_bytes = output.getvalue().encode("utf-8")

        # 3. Загружаем CSV в хранилище RustFS (S3)
        storage_key = f"reports/report_{report_id}.csv"
        try:
            storage_client.put_object(
                bucket_name="documents",
                object_name=storage_key,
                data=io.BytesIO(csv_bytes),
                length=len(csv_bytes),
                content_type="text/csv"
            )
            download_url = f"/api/reports/{report_id}/download"
            log.info("report %s saved to S3: %s", report_id, storage_key)
        except Exception as e:
            log.exception("failed to upload report to S3")
            download_url = None

        # 4. Отправляем уведомление финансовому подразделению (external-stubs)
        try:
            finance_url = os.environ.get("FINANCE_URL", "http://external-stubs:8081/finance/reports")
            finance_token = os.environ.get("FINANCE_API_TOKEN", "")
            httpx.post(
                finance_url,
                json={"report_id": report_id, "download_url": download_url, "records_count": len(rows)},
                headers={"Authorization": f"Bearer {finance_token}"},
                timeout=5.0
            )
            log.info("notified finance stub about report %s", report_id)
        except Exception as e:
            log.exception("failed to notify finance stub")

        # 5. Обновляем статус отчёта в Redis
        report_data = {
            "report_id": report_id,
            "status": "completed",
            "download_url": download_url,
            "expires_at": int(time.time()) + 86400,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        r.setex(f"report:{report_id}", 86400, json.dumps(report_data))


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

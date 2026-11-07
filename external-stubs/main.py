"""Заглушки внешних систем: финансовое подразделение (B-11) и система мониторинга (B-12).
Сохраняют контракт взаимодействия из ЛР №2: приём по HTTPS/JSON с API-токеном
(в локальной сети без TLS – см. журнал расхождений)."""
import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stubs")
FIN = os.environ["FINANCE_API_TOKEN"]
MON = os.environ["MONITORING_API_TOKEN"]
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_reports: dict[str, dict] = {}


def _check(auth: str | None, expected: str) -> None:
    # сравнение за постоянное время; без токена или с чужим – 401
    if not auth or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], expected):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.post("/finance/reports", status_code=202)
async def finance_report(request: Request, authorization: str | None = Header(None)):
    """Приём уведомления «сводный отчёт готов» (B-11): идентификатор, ссылка, срок действия.
    Сами файлы и выплаты финансовому подразделению не передаются."""
    _check(authorization, FIN)
    body = await request.json()
    key = str(body.get("report_id", ""))
    if not key:
        raise HTTPException(status_code=422, detail="report_id required")
    first = key not in _reports
    _reports.setdefault(key, body)  # повтор того же report_id не создаёт второй записи
    log.info("finance: report %s received (new=%s) url=%s", key, first, body.get("download_url"))
    return {"accepted": True, "duplicate": not first}


@app.post("/metrics", status_code=204)
async def metrics(request: Request, authorization: str | None = Header(None)):
    _check(authorization, MON)
    body = await request.body()
    if len(body) > 4096:
        raise HTTPException(status_code=413, detail="too large")
    log.info("metric: %s", body.decode("utf-8", "replace"))

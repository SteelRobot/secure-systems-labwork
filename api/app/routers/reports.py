import json
import time
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from .. import config
from ..cache import r as redis_client
from ..db import pool
from ..broker import publish
from ..deps import CurrentUser, get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])

class ReportResponse(BaseModel):
    report_id: str
    status: str
    download_url: str | None = None
    expires_at: int | None = None
    created_at: str

@router.get("/applications", status_code=status.HTTP_202_ACCEPTED, response_model=ReportResponse)
def generate_applications_report(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    date_from: str | None = None,
    date_to: str | None = None,
    format: str = "csv"
):
    ip = request.client.host if request.client else "127.0.0.1"

    # Только ответственные сотрудники могут формировать сводный отчёт
    if user.role != "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только ответственный сотрудник может формировать сводный отчёт"
        )

    if not user.department_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Сотрудник не привязан к подразделению"
        )

    # Ограничение частоты: не более 5 отчётов в час
    rate_key = f"rate:report:{user.id}"
    attempts = redis_client.incr(rate_key)
    if attempts == 1:
        redis_client.expire(rate_key, 3600)
    if attempts > 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Превышена частота формирования отчётов (максимум 5 в час)"
        )

    # Идемпотентность по Idempotency-Key
    if idempotency_key:
        idem_key = f"idem:report:{user.id}:{idempotency_key}"
        cached = redis_client.get(idem_key)
        if cached:
            return ReportResponse(**json.loads(cached))

    report_uuid = str(uuid4())
    now_ts = int(time.time())

    report_data = {
        "report_id": report_uuid,
        "status": "processing",
        "download_url": None,
        "expires_at": None,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts))
    }

    # Сохраняем состояние задачи отчёта в Redis
    redis_client.setex(f"report:{report_uuid}", 86400, json.dumps(report_data))

    # Отправка задачи воркеру в очередь reports
    publish("reports", {
        "task": "generate_report",
        "report_id": report_uuid,
        "department_id": user.department_id,
        "requested_by": user.id,
        "date_from": date_from,
        "date_to": date_to,
        "format": format
    })

    publish("audit", {
        "actor_user_id": user.id,
        "action": "report.generate.started",
        "entity_type": "report",
        "entity_id": report_uuid,
        "details": {"department_id": user.department_id, "format": format},
        "ip_address": ip,
    })

    res = ReportResponse(**report_data)

    if idempotency_key:
        redis_client.setex(f"idem:report:{user.id}:{idempotency_key}", 86400, res.model_dump_json())

    return res

@router.get("/{report_id}", response_model=ReportResponse)
def get_report_status(
    report_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    if user.role not in ("employee", "technical_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    data_str = redis_client.get(f"report:{report_id}")
    if not data_str:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отчёт не найден")

    return ReportResponse(**json.loads(data_str))


from fastapi.responses import StreamingResponse

@router.get("/{report_id}/download")
def download_report_file(
    report_id: str,
    user: CurrentUser = Depends(get_current_user)
):
    if user.role not in ("employee", "technical_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    data_str = redis_client.get(f"report:{report_id}")
    if not data_str:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отчёт не найден")

    report_info = json.loads(data_str)
    if report_info.get("status") != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Отчёт ещё не сформирован")

    storage_key = f"reports/report_{report_id}.csv"
    from ..storage import client as storage_client
    try:
        response = storage_client.get_object(config.STORAGE_BUCKET, storage_key)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл отчёта не найден в хранилище")

    return StreamingResponse(
        response.stream(32768),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="report_{report_id}.csv"'}
    )

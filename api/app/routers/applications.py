from pathlib import Path
import json
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from .. import config
from ..cache import r as redis_client
from ..db import pool
from ..broker import publish
from ..deps import CurrentUser, get_current_user

router = APIRouter(prefix="/api/applications", tags=["applications"])

class CreateApplicationRequest(BaseModel):
    support_type: str = Field(..., description="material_support, state_academic_scholarship, pgas")
    academic_year: int = Field(..., ge=2000, le=2100)
    requested_amount: float | None = Field(None, gt=0)
    comment: str = Field(..., min_length=1, max_length=5000)

class DocumentItem(BaseModel):
    id: str
    original_name: str
    file_size: int
    mime_type: str
    uploaded_at: str
    download_url: str

class ApplicationDetailResponse(BaseModel):
    id: str
    applicant_id: str
    support_type: str
    academic_year: int
    status: str
    requested_amount: float | None
    approved_amount: float | None
    comment: str | None
    decision_comment: str | None
    created_at: str
    submitted_at: str | None
    updated_at: str
    documents: list[DocumentItem] = []

VALID_SUPPORT_TYPES = {"material_support", "state_academic_scholarship", "pgas"}

@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApplicationDetailResponse)
def create_application(
    req: CreateApplicationRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key")
):
    ip = request.client.host if request.client else "127.0.0.1"

    # Создавать заявку могут только роли заявителей (student, employee)
    if user.role != "applicant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Создавать заявки может только заявитель"
        )

    if req.support_type not in VALID_SUPPORT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Недопустимый тип поддержки. Допустимы: {', '.join(VALID_SUPPORT_TYPES)}"
        )

    # 1. Rate limiting: не более 5 заявок в час на пользователя
    rate_key = f"rate:app_create:{user.id}"
    attempts = redis_client.incr(rate_key)
    if attempts == 1:
        redis_client.expire(rate_key, 3600)
    if attempts > 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Превышен лимит создания заявок (не более 5 в час)"
        )

    # 2. Идемпотентность по Idempotency-Key
    if idempotency_key:
        idem_key = f"idem:app_create:{user.id}:{idempotency_key}"
        cached_resp = redis_client.get(idem_key)
        if cached_resp:
            return ApplicationDetailResponse(**json.loads(cached_resp))

    # 3. Вставка записи под ролью app_api
    with pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO applications (applicant_id, support_type, academic_year, requested_amount, comment, status)
               VALUES (%s, %s, %s, %s, %s, 'submitted')
               RETURNING id, applicant_id, support_type, academic_year, status, requested_amount,
                         approved_amount, comment, decision_comment, created_at, submitted_at, updated_at""",
            (user.id, req.support_type, req.academic_year, req.requested_amount, req.comment)
        ).fetchone()
        conn.commit()

    res = ApplicationDetailResponse(
        id=str(row["id"]),
        applicant_id=str(row["applicant_id"]),
        support_type=row["support_type"],
        academic_year=row["academic_year"],
        status=row["status"],
        requested_amount=float(row["requested_amount"]) if row["requested_amount"] is not None else None,
        approved_amount=float(row["approved_amount"]) if row["approved_amount"] is not None else None,
        comment=row["comment"],
        decision_comment=row["decision_comment"],
        created_at=row["created_at"].isoformat(),
        submitted_at=row["submitted_at"].isoformat() if row["submitted_at"] else None,
        updated_at=row["updated_at"].isoformat(),
        documents=[]
    )

    if idempotency_key:
        redis_client.setex(f"idem:app_create:{user.id}:{idempotency_key}", 86400, res.model_dump_json())

    publish("audit", {
        "actor_user_id": user.id,
        "action": "application.create",
        "entity_type": "application",
        "entity_id": str(row["id"]),
        "details": {"support_type": req.support_type, "academic_year": req.academic_year},
        "ip_address": ip,
    })

    return res

@router.get("/{app_id}", response_model=ApplicationDetailResponse)
def get_application_by_id(
    app_id: UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user)
):
    ip = request.client.host if request.client else "127.0.0.1"

    with pool.connection() as conn:
        # Получение заявки с привязкой к подразделению заявителя (JOIN users)
        row = conn.execute(
            """SELECT a.id, a.applicant_id, a.support_type, a.academic_year, a.status,
                      a.requested_amount, a.approved_amount, a.comment, a.decision_comment,
                      a.created_at, a.submitted_at, a.updated_at,
                      u.department_id as applicant_department_id
               FROM applications a
               JOIN users u ON u.id = a.applicant_id
               WHERE a.id = %s""",
            (str(app_id),)
        ).fetchone()

        if not row:
            publish("audit", {
                "actor_user_id": user.id,
                "action": "application.read.failed",
                "entity_type": "application",
                "entity_id": str(app_id),
                "details": {"reason": "not_found"},
                "ip_address": ip,
            })
            # По контракту ЛР №2: 404 если не найдена или нет прав
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        # Проверка прав доступа к объекту
        has_access = False
        if user.role == "applicant":
            # Заявитель видит только свои заявки
            has_access = (str(row["applicant_id"]) == user.id)
        elif user.role == "employee":
            # Ответственный сотрудник видит заявки своего подразделения, НО не черновики (status != 'draft')
            has_access = (
                user.department_id is not None and
                str(row["applicant_department_id"]) == user.department_id and
                row["status"] != "draft"
            )
        elif user.role == "technical_admin":
            has_access = True

        if not has_access:
            publish("audit", {
                "actor_user_id": user.id,
                "action": "application.read.denied",
                "entity_type": "application",
                "entity_id": str(app_id),
                "details": {"reason": "forbidden_object"},
                "ip_address": ip,
            })
            # 404 вместо 403, чтобы нарушитель не узнал о существовании чужой заявки
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        # Получаем прикрепленные документы
        doc_rows = conn.execute(
            """SELECT id, original_name, file_size, mime_type, uploaded_at
               FROM documents WHERE application_id = %s ORDER BY uploaded_at ASC""",
            (str(app_id),)
        ).fetchall()

    documents = [
        DocumentItem(
            id=str(d["id"]),
            original_name=d["original_name"],
            file_size=d["file_size"],
            mime_type=d["mime_type"],
            uploaded_at=d["uploaded_at"].isoformat(),
            download_url=f"/api/applications/{app_id}/documents/{d['id']}"
        )
        for d in doc_rows
    ]

    publish("audit", {
        "actor_user_id": user.id,
        "action": "application.read.success",
        "entity_type": "application",
        "entity_id": str(app_id),
        "details": {},
        "ip_address": ip,
    })

    return ApplicationDetailResponse(
        id=str(row["id"]),
        applicant_id=str(row["applicant_id"]),
        support_type=row["support_type"],
        academic_year=row["academic_year"],
        status=row["status"],
        requested_amount=float(row["requested_amount"]) if row["requested_amount"] is not None else None,
        approved_amount=float(row["approved_amount"]) if row["approved_amount"] is not None else None,
        comment=row["comment"],
        decision_comment=row["decision_comment"],
        created_at=row["created_at"].isoformat(),
        submitted_at=row["submitted_at"].isoformat() if row["submitted_at"] else None,
        updated_at=row["updated_at"].isoformat(),
        documents=documents
    )


class ApplicationListItem(BaseModel):
    id: str
    applicant_id: str
    support_type: str
    academic_year: int
    status: str
    requested_amount: float | None
    created_at: str

class ApplicationListResponse(BaseModel):
    items: list[ApplicationListItem]
    total: int
    page: int
    page_size: int

@router.get("", response_model=ApplicationListResponse)
def get_applications_list(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    status_filter: str | None = None,
    support_type_filter: str | None = None,
    academic_year_filter: int | None = None,
    page: int = 1,
    page_size: int = 20,
):
    ip = request.client.host if request.client else "127.0.0.1"

    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Некорректные параметры пагинации (page >= 1, 1 <= page_size <= 100)"
        )

    offset = (page - 1) * page_size

    # Базовый SQL запрос с автоматической фильтрацией прав
    # - Для студентов/сотрудников: только свои заявки (applicant_id = user.id)
    # - Для ответственного сотрудника: только заявки своего подразделения (JOIN users)
    where_clauses = []
    params = []

    if user.role == "applicant":
        where_clauses.append("a.applicant_id = %s")
        params.append(user.id)
    elif user.role == "employee":
        if not user.department_id:
            return ApplicationListResponse(items=[], total=0, page=page, page_size=page_size)
        where_clauses.append("u.department_id = %s")
        params.append(user.department_id)
        # Ответственный сотрудник НЕ видит чужие черновики
        where_clauses.append("a.status != 'draft'")
    elif user.role == "technical_admin":
        # Намеренно без фильтра: администратор видит все заявки.
        pass
    else:
        # Неизвестная или неподдерживаемая роль — доступ запрещён.
        raise PermissionError("Role is not allowed to list applications")

    if status_filter:
        where_clauses.append("a.status = %s")
        params.append(status_filter)

    if support_type_filter:
        where_clauses.append("a.support_type = %s")
        params.append(support_type_filter)

    if academic_year_filter:
        where_clauses.append("a.academic_year = %s")
        params.append(academic_year_filter)

    where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    with pool.connection() as conn:
        count_sql = f"SELECT count(*) FROM applications a JOIN users u ON u.id = a.applicant_id{where_sql}"
        total = conn.execute(count_sql, params).fetchone()["count"]

        query_sql = f"""
            SELECT a.id, a.applicant_id, a.support_type, a.academic_year, a.status,
                   a.requested_amount, a.created_at
            FROM applications a
            JOIN users u ON u.id = a.applicant_id
            {where_sql}
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
        """
        rows = conn.execute(query_sql, params + [page_size, offset]).fetchall()

    items = [
        ApplicationListItem(
            id=str(r["id"]),
            applicant_id=str(r["applicant_id"]),
            support_type=r["support_type"],
            academic_year=r["academic_year"],
            status=r["status"],
            requested_amount=float(r["requested_amount"]) if r["requested_amount"] is not None else None,
            created_at=r["created_at"].isoformat()
        )
        for r in rows
    ]

    publish("audit", {
        "actor_user_id": user.id,
        "action": "application.list",
        "entity_type": "application",
        "entity_id": None,
        "details": {"total": total, "page": page, "status_filter": status_filter},
        "ip_address": ip,
    })

    return ApplicationListResponse(items=items, total=total, page=page, page_size=page_size)


import hashlib
from fastapi import UploadFile, File

ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

class DocumentUploadResponse(BaseModel):
    id: str
    application_id: str
    original_name: str
    file_size: int
    mime_type: str
    sha256_hash: str
    uploaded_at: str

@router.post("/{app_id}/documents", status_code=status.HTTP_201_CREATED, response_model=DocumentUploadResponse)
async def upload_document(
    app_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    ip = request.client.host if request.client else "127.0.0.1"

    # 1. Проверка существования заявки и прав владельца
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, applicant_id, status FROM applications WHERE id = %s",
            (str(app_id),)
        ).fetchone()

        if not row or str(row["applicant_id"]) != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        if row["status"] not in ("draft", "needs_revision"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Документы можно загружать только в черновик или заявку на доработке"
            )

        # Ограничение: не более 10 документов на заявку
        doc_count = conn.execute(
            "SELECT count(*) FROM documents WHERE application_id = %s",
            (str(app_id),)
        ).fetchone()["count"]
        if doc_count >= 10:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Превышен лимит документов (максимум 10 на заявку)"
            )

    # 2. Проверка типа файла
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Недопустимый формат файла. Разрешены: PDF, PNG, JPEG"
        )

    # 3. Чтение файла, подсчет размера и SHA-256
    file_bytes = await file.read()
    file_size = len(file_bytes)
    if file_size == 0 or file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Размер файла должен быть больше 0 и не превышать 10 МБ"
        )

    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    doc_uuid = str(uuid4())
    safe_name = Path(file.filename or "file").name
    storage_key = f"applications/{app_id}/{doc_uuid}_{safe_name}"

    # 4. Сохранение файла в объектное хранилище (RustFS S3 API)
    from io import BytesIO
    from ..storage import client as storage_client

    try:
        storage_client.put_object(
            bucket_name=config.STORAGE_BUCKET,
            object_name=storage_key,
            data=BytesIO(file_bytes),
            length=file_size,
            content_type=content_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при сохранении файла в хранилище"
        )

    # 5. Запись метаданных в базу данных
    with pool.connection() as conn:
        doc_row = conn.execute(
            """INSERT INTO documents (id, application_id, uploaded_by, original_name, storage_key, mime_type, file_size, sha256_hash)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, application_id, original_name, file_size, mime_type, sha256_hash, uploaded_at""",
            (doc_uuid, str(app_id), user.id, safe_name, storage_key, content_type, file_size, sha256_hash)
        ).fetchone()
        conn.commit()

    publish("audit", {
        "actor_user_id": user.id,
        "action": "document.upload",
        "entity_type": "document",
        "entity_id": str(doc_row["id"]),
        "details": {"application_id": str(app_id), "file_name": safe_name, "file_size": file_size},
        "ip_address": ip,
    })

    return DocumentUploadResponse(
        id=str(doc_row["id"]),
        application_id=str(doc_row["application_id"]),
        original_name=doc_row["original_name"],
        file_size=doc_row["file_size"],
        mime_type=doc_row["mime_type"],
        sha256_hash=doc_row["sha256_hash"],
        uploaded_at=doc_row["uploaded_at"].isoformat()
    )


from fastapi.responses import StreamingResponse

@router.get("/{app_id}/documents/{doc_id}")
def download_document(
    app_id: UUID,
    doc_id: UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    ip = request.client.host if request.client else "127.0.0.1"

    with pool.connection() as conn:
        # Check application access rights
        app_row = conn.execute(
            """SELECT a.id, a.applicant_id, a.status, u.department_id as applicant_department_id
               FROM applications a
               JOIN users u ON u.id = a.applicant_id
               WHERE a.id = %s""",
            (str(app_id),)
        ).fetchone()

        if not app_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        has_access = False
        if user.role == "applicant":
            has_access = (str(app_row["applicant_id"]) == user.id)
        elif user.role == "employee":
            has_access = (
                user.department_id is not None and
                str(app_row["applicant_department_id"]) == user.department_id and
                app_row["status"] != "draft"
            )
        elif user.role == "technical_admin":
            has_access = True

        if not has_access:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        doc_row = conn.execute(
            "SELECT id, original_name, storage_key, mime_type, file_size FROM documents WHERE id = %s AND application_id = %s",
            (str(doc_id), str(app_id))
        ).fetchone()

        if not doc_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ не найден")

    # Read stream from RustFS S3
    from ..storage import client as storage_client
    try:
        response = storage_client.get_object(config.STORAGE_BUCKET, doc_row["storage_key"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден в хранилище")

    publish("audit", {
        "actor_user_id": user.id,
        "action": "document.download",
        "entity_type": "document",
        "entity_id": str(doc_id),
        "details": {"application_id": str(app_id)},
        "ip_address": ip,
    })

    return StreamingResponse(
        response.stream(32768),
        media_type=doc_row["mime_type"],
        headers={"Content-Disposition": f'inline; filename="{doc_row["original_name"]}"'}
    )


@router.patch("/{app_id}/submit", response_model=ApplicationDetailResponse)
def submit_application(
    app_id: UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key")
):
    ip = request.client.host if request.client else "127.0.0.1"

    if user.role != "applicant":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Отправлять заявку может только заявитель")

    # Идемпотентность
    if idempotency_key:
        idem_key = f"idem:app_submit:{user.id}:{idempotency_key}"
        cached_resp = redis_client.get(idem_key)
        if cached_resp:
            return ApplicationDetailResponse(**json.loads(cached_resp))

    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, applicant_id, status FROM applications WHERE id = %s",
            (str(app_id),)
        ).fetchone()

        if not row or str(row["applicant_id"]) != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        if row["status"] not in ("draft", "needs_revision"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Заявка уже отправлена или обработана")

        # Перевод статуса draft / needs_revision -> submitted
        updated_row = conn.execute(
            """UPDATE applications
               SET status = 'submitted',
                   submitted_at = COALESCE(submitted_at, CURRENT_TIMESTAMP),
                   updated_at = CURRENT_TIMESTAMP,
                   version = version + 1
               WHERE id = %s AND status IN ('draft', 'needs_revision')
               RETURNING id, applicant_id, support_type, academic_year, status, requested_amount,
                         approved_amount, comment, decision_comment, created_at, submitted_at, updated_at""",
            (str(app_id),)
        ).fetchone()
        conn.commit()

        doc_rows = conn.execute(
            "SELECT id, original_name, file_size, mime_type, uploaded_at FROM documents WHERE application_id = %s",
            (str(app_id),)
        ).fetchall()

    documents = [
        DocumentItem(
            id=str(d["id"]),
            original_name=d["original_name"],
            file_size=d["file_size"],
            mime_type=d["mime_type"],
            uploaded_at=d["uploaded_at"].isoformat(),
            download_url=f"/api/applications/{app_id}/documents/{d['id']}"
        )
        for d in doc_rows
    ]

    res = ApplicationDetailResponse(
        id=str(updated_row["id"]),
        applicant_id=str(updated_row["applicant_id"]),
        support_type=updated_row["support_type"],
        academic_year=updated_row["academic_year"],
        status=updated_row["status"],
        requested_amount=float(updated_row["requested_amount"]) if updated_row["requested_amount"] is not None else None,
        approved_amount=float(updated_row["approved_amount"]) if updated_row["approved_amount"] is not None else None,
        comment=updated_row["comment"],
        decision_comment=updated_row["decision_comment"],
        created_at=updated_row["created_at"].isoformat(),
        submitted_at=updated_row["submitted_at"].isoformat() if updated_row["submitted_at"] else None,
        updated_at=updated_row["updated_at"].isoformat(),
        documents=documents
    )

    if idempotency_key:
        redis_client.setex(f"idem:app_submit:{user.id}:{idempotency_key}", 86400, res.model_dump_json())

    publish("audit", {
        "actor_user_id": user.id,
        "action": "application.submit",
        "entity_type": "application",
        "entity_id": str(app_id),
        "details": {"previous_status": "draft", "new_status": "submitted"},
        "ip_address": ip,
    })

    return res


class StatusChangeRequest(BaseModel):
    status: str = Field(..., description="under_review, needs_revision, approved, rejected, cancelled")
    decision_comment: str | None = Field(None, max_length=2000)
    approved_amount: float | None = Field(None, ge=0)

VALID_STATUS_TRANSITIONS = {
    "submitted": {"under_review", "cancelled"},
    "under_review": {"needs_revision", "approved", "rejected", "cancelled"},
    "needs_revision": {"submitted", "cancelled"},
}

@router.patch("/{app_id}/status", response_model=ApplicationDetailResponse)
def update_application_status(
    app_id: UUID,
    req: StatusChangeRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key")
):
    ip = request.client.host if request.client else "127.0.0.1"

    if user.role not in ("employee", "applicant"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    # Идемпотентность
    if idempotency_key:
        idem_key = f"idem:app_status:{user.id}:{idempotency_key}"
        cached_resp = redis_client.get(idem_key)
        if cached_resp:
            return ApplicationDetailResponse(**json.loads(cached_resp))

    with pool.connection() as conn:
        row = conn.execute(
            """SELECT a.id, a.applicant_id, a.status, a.requested_amount, a.version, u.department_id as applicant_department_id
               FROM applications a
               JOIN users u ON u.id = a.applicant_id
               WHERE a.id = %s""",
            (str(app_id),)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        curr_status = row["status"]

        # Заявитель может только отозвать свой черновик/отправленную заявку (cancelled)
        if user.role == "applicant":
            if str(row["applicant_id"]) != user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
            if req.status != "cancelled":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Заявитель может только отозвать заявку")
            if curr_status not in ("draft", "submitted", "needs_revision"):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Нельзя отозвать обработанную заявку")

        # Ответственный сотрудник может менять статус заявок своего подразделения (status != draft)
        elif user.role == "employee":
            if not user.department_id or str(row["applicant_department_id"]) != user.department_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
            if curr_status == "draft":
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

            # Валидация перехода статуса
            allowed = VALID_STATUS_TRANSITIONS.get(curr_status, set())
            if req.status not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Недопустимый переход из статуса '{curr_status}' в '{req.status}'"
                )

            # Если выставляется одобренная сумма — она не должна превышать запрашиваемую
            if req.status == "approved" and req.approved_amount is not None:
                req_amount = float(row["requested_amount"]) if row["requested_amount"] is not None else None
                if req_amount is not None and req.approved_amount > req_amount:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Одобренная сумма не может превышать запрашиваемую"
                    )

        # Выполнение обновления в БД
        updated_row = conn.execute(
            """UPDATE applications
               SET status = %s,
                   decision_comment = COALESCE(%s, decision_comment),
                   approved_amount = COALESCE(%s, approved_amount),
                   reviewed_by = %s,
                   reviewed_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP,
                   version = version + 1
               WHERE id = %s AND version = %s
               RETURNING id, applicant_id, support_type, academic_year, status, requested_amount,
                         approved_amount, comment, decision_comment, created_at, submitted_at, updated_at""",
            (req.status, req.decision_comment, req.approved_amount, user.id, str(app_id), row["version"])
        ).fetchone()

        if not updated_row:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Конфликт версии заявки")

        conn.commit()

        doc_rows = conn.execute(
            "SELECT id, original_name, file_size, mime_type, uploaded_at FROM documents WHERE application_id = %s",
            (str(app_id),)
        ).fetchall()

    documents = [
        DocumentItem(
            id=str(d["id"]),
            original_name=d["original_name"],
            file_size=d["file_size"],
            mime_type=d["mime_type"],
            uploaded_at=d["uploaded_at"].isoformat(),
            download_url=f"/api/applications/{app_id}/documents/{d['id']}"
        )
        for d in doc_rows
    ]

    res = ApplicationDetailResponse(
        id=str(updated_row["id"]),
        applicant_id=str(updated_row["applicant_id"]),
        support_type=updated_row["support_type"],
        academic_year=updated_row["academic_year"],
        status=updated_row["status"],
        requested_amount=float(updated_row["requested_amount"]) if updated_row["requested_amount"] is not None else None,
        approved_amount=float(updated_row["approved_amount"]) if updated_row["approved_amount"] is not None else None,
        comment=updated_row["comment"],
        decision_comment=updated_row["decision_comment"],
        created_at=updated_row["created_at"].isoformat(),
        submitted_at=updated_row["submitted_at"].isoformat() if updated_row["submitted_at"] else None,
        updated_at=updated_row["updated_at"].isoformat(),
        documents=documents
    )

    if idempotency_key:
        redis_client.setex(f"idem:app_status:{user.id}:{idempotency_key}", 86400, res.model_dump_json())

    publish("audit", {
        "actor_user_id": user.id,
        "action": "application.status_update",
        "entity_type": "application",
        "entity_id": str(app_id),
        "details": {"previous_status": curr_status, "new_status": req.status, "comment": req.decision_comment},
        "ip_address": ip,
    })

    return res


class LLMCheckResponse(BaseModel):
    id: str
    application_id: str
    check_type: str
    status: str
    is_complete: bool
    issues: list[str] = []
    recommendations: list[str] = []
    model_version: str | None
    created_at: str
    completed_at: str | None

@router.post("/{app_id}/completeness-check", status_code=status.HTTP_202_ACCEPTED, response_model=LLMCheckResponse)
def trigger_completeness_check(
    app_id: UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key")
):
    ip = request.client.host if request.client else "127.0.0.1"

    with pool.connection() as conn:
        app_row = conn.execute(
            """SELECT a.id, a.applicant_id, a.status, u.department_id as applicant_department_id
               FROM applications a
               JOIN users u ON u.id = a.applicant_id
               WHERE a.id = %s""",
            (str(app_id),)
        ).fetchone()

        if not app_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        # Запускать ИИ-проверку может заявитель для своих неокончательных заявок
        # или ответственный сотрудник своего подразделения для незавершённых заявок
        has_access = False
        if user.role == "applicant":
            has_access = (str(app_row["applicant_id"]) == user.id)
        elif user.role == "employee":
            has_access = (
                user.department_id is not None and
                str(app_row["applicant_department_id"]) == user.department_id and
                app_row["status"] != "draft"
            )
        elif user.role == "technical_admin":
            has_access = True

        if not has_access:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        # Проверка допустима только для незавершённых заявок (не approved, rejected, cancelled)
        if app_row["status"] in ("approved", "rejected", "cancelled"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Проверка полноты доступна только для незавершённых заявок"
            )

        # Check rate limiting: max 3 checks per application per hour
        check_rate_key = f"rate:llm_check:{app_id}"
        attempts = redis_client.incr(check_rate_key)
        if attempts == 1:
            redis_client.expire(check_rate_key, 3600)
        if attempts > 3:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Превышен лимит проверок для этой заявки")

        # Check if a check is already processing
        active = conn.execute(
            "SELECT id FROM llm_checks WHERE application_id = %s AND status IN ('queued', 'processing')",
            (str(app_id),)
        ).fetchone()
        if active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Проверка данной заявки уже выполняется")

        # Create record in llm_checks
        check_uuid = str(uuid4())
        check_row = conn.execute(
            """INSERT INTO llm_checks (id, application_id, requested_by, check_type, status, model_version)
               VALUES (%s, %s, %s, 'completeness', 'queued', 'mock-llm-v1.0')
               RETURNING id, application_id, check_type, status, is_complete, issues, recommendations, model_version, created_at, completed_at""",
            (check_uuid, str(app_id), user.id)
        ).fetchone()
        conn.commit()

    publish("notifications", {
        "task": "llm_check",
        "check_id": check_uuid,
        "application_id": str(app_id)
    })

    publish("audit", {
        "actor_user_id": user.id,
        "action": "application.llm_check.started",
        "entity_type": "llm_check",
        "entity_id": check_uuid,
        "details": {"application_id": str(app_id)},
        "ip_address": ip,
    })

    return LLMCheckResponse(
        id=str(check_row["id"]),
        application_id=str(check_row["application_id"]),
        check_type=check_row["check_type"],
        status=check_row["status"],
        is_complete=check_row["is_complete"],
        issues=check_row["issues"],
        recommendations=check_row["recommendations"],
        model_version=check_row["model_version"],
        created_at=check_row["created_at"].isoformat(),
        completed_at=check_row["completed_at"].isoformat() if check_row["completed_at"] else None
    )

@router.get("/{app_id}/completeness-check", response_model=list[LLMCheckResponse])
def get_application_checks(
    app_id: UUID,
    request: Request,
    user: CurrentUser = Depends(get_current_user)
):
    with pool.connection() as conn:
        app_row = conn.execute(
            """SELECT a.id, a.applicant_id, a.status, u.department_id as applicant_department_id
               FROM applications a
               JOIN users u ON u.id = a.applicant_id
               WHERE a.id = %s""",
            (str(app_id),)
        ).fetchone()

        if not app_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        has_access = False
        if user.role == "applicant":
            has_access = (str(app_row["applicant_id"]) == user.id)
        elif user.role == "employee":
            has_access = (
                user.department_id is not None and
                str(app_row["applicant_department_id"]) == user.department_id and
                app_row["status"] != "draft"
            )
        elif user.role == "technical_admin":
            has_access = True

        if not has_access:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")

        rows = conn.execute(
            """SELECT id, application_id, check_type, status, is_complete, issues, recommendations, model_version, created_at, completed_at
               FROM llm_checks WHERE application_id = %s ORDER BY created_at DESC""",
            (str(app_id),)
        ).fetchall()

    return [
        LLMCheckResponse(
            id=str(r["id"]),
            application_id=str(r["application_id"]),
            check_type=r["check_type"],
            status=r["status"],
            is_complete=r["is_complete"],
            issues=r["issues"] if isinstance(r["issues"], list) else json.loads(r["issues"]),
            recommendations=r["recommendations"] if isinstance(r["recommendations"], list) else json.loads(r["recommendations"]),
            model_version=r["model_version"],
            created_at=r["created_at"].isoformat(),
            completed_at=r["completed_at"].isoformat() if r["completed_at"] else None
        )
        for r in rows
    ]

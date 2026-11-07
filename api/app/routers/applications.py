import json
from uuid import UUID
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
               VALUES (%s, %s, %s, %s, %s, 'draft')
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
            uploaded_at=d["uploaded_at"].isoformat()
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

import time
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
import jwt

from .. import config
from ..cache import r as redis_client
from ..db import pool
from ..broker import publish
from ..security import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    role: str
    department_id: str | None

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request):
    ip = request.client.host if request.client else "127.0.0.1"

    # 1. Rate limiting (не более 10 попыток в минуту с одного IP)
    rate_key = f"rate:login:{ip}"
    attempts = redis_client.incr(rate_key)
    if attempts == 1:
        redis_client.expire(rate_key, 60)
    if attempts > 10:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа. Попробуйте позже."
        )

    email_clean = req.email.strip().lower()
    if not email_clean or not req.password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email и пароль обязательны")

    # 2. Поиск пользователя под ролью app_api
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT id, full_name, email, role, password_hash, password_salt, department_id, is_active
               FROM users WHERE lower(email) = %s""",
            (email_clean,)
        ).fetchone()

    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный логин или пароль"
    )

    if not row or not row["is_active"]:
        time.sleep(0.05)
        publish("audit", {
            "actor_user_id": None,
            "action": "auth.login.failed",
            "entity_type": "user",
            "entity_id": None,
            "details": {"email": email_clean, "reason": "user_not_found"},
            "ip_address": ip,
        })
        raise invalid_exc

    # 3. Проверка пароля (Argon2id + pepper)
    if not verify_password(req.password, row["password_hash"], config.PASSWORD_PEPPER):
        publish("audit", {
            "actor_user_id": str(row["id"]),
            "action": "auth.login.failed",
            "entity_type": "user",
            "entity_id": str(row["id"]),
            "details": {"email": email_clean, "reason": "invalid_password"},
            "ip_address": ip,
        })
        raise invalid_exc

    # 4. Выпуск JWT и сохранение сессии в Redis
    jti = str(uuid4())
    now = int(time.time())
    ttl = config.ACCESS_TOKEN_TTL

    payload = {
        "sub": str(row["id"]),
        "role": row["role"],
        "department_id": str(row["department_id"]) if row["department_id"] else None,
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
    }

    token = jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

    # Сессия в Redis по jti
    redis_client.setex(f"session:{jti}", ttl, str(row["id"]))

    # Запись удачного входа в аудит через брокер
    publish("audit", {
        "actor_user_id": str(row["id"]),
        "action": "auth.login.success",
        "entity_type": "user",
        "entity_id": str(row["id"]),
        "details": {"email": email_clean, "role": row["role"]},
        "ip_address": ip,
    })

    return LoginResponse(
        access_token=token,
        token_type="Bearer",
        expires_in=ttl,
        user=UserResponse(
            id=str(row["id"]),
            full_name=row["full_name"],
            email=row["email"],
            role=row["role"],
            department_id=str(row["department_id"]) if row["department_id"] else None
        )
    )

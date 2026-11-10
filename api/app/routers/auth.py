import time
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request, status, Header
from pydantic import BaseModel, EmailStr, Field
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


class RegisterRequest(BaseModel):
    university_id: str = Field(..., min_length=2, max_length=32)
    full_name: str = Field(..., min_length=2, max_length=200)
    email: str
    password: str = Field(..., min_length=8)
    department_id: str | None = None

class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirmRequest(BaseModel):
    email: str
    reset_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8)

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def register(req: RegisterRequest, request: Request):
    ip = request.client.host if request.client else "127.0.0.1"

    email_clean = req.email.strip().lower()

    # Rate limiting: max 5 registrations per hour per IP
    rate_key = f"rate:register:{ip}"
    attempts = redis_client.incr(rate_key)
    if attempts == 1:
        redis_client.expire(rate_key, 3600)
    if attempts > 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Превышен лимит регистраций с этого IP"
        )

    # Hash password with Argon2id + pepper
    from ..security import hash_password
    pwd_hash, pwd_salt = hash_password(req.password, config.PASSWORD_PEPPER)

    with pool.connection() as conn:
        # Check uniqueness of university_id / email
        existing = conn.execute(
            "SELECT id FROM users WHERE lower(email) = %s OR university_id = %s",
            (email_clean, req.university_id)
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Пользователь с таким email или номером уже зарегистрирован"
            )

        row = conn.execute(
            """INSERT INTO users (university_id, full_name, email, role, password_hash, password_salt, department_id)
               VALUES (%s, %s, %s, 'applicant', %s, %s, %s)
               RETURNING id, full_name, email, role, department_id""",
            (req.university_id, req.full_name, email_clean, pwd_hash, pwd_salt, req.department_id)
        ).fetchone()
        conn.commit()

    publish("audit", {
        "actor_user_id": str(row["id"]),
        "action": "auth.register",
        "entity_type": "user",
        "entity_id": str(row["id"]),
        "details": {"email": email_clean, "university_id": req.university_id},
        "ip_address": ip,
    })

    return UserResponse(
        id=str(row["id"]),
        full_name=row["full_name"],
        email=row["email"],
        role=row["role"],
        department_id=str(row["department_id"]) if row["department_id"] else None
    )

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    authorization: str | None = Header(None)
):
    ip = request.client.host if request.client else "127.0.0.1"

    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        try:
            payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
            jti = payload.get("jti")
            user_id = payload.get("sub")
            if jti:
                # Delete session key in Redis -> invalidates token
                redis_client.delete(f"session:{jti}")
                publish("audit", {
                    "actor_user_id": user_id,
                    "action": "auth.logout",
                    "entity_type": "user",
                    "entity_id": user_id,
                    "details": {},
                    "ip_address": ip,
                })
        except jwt.PyJWTError:
            pass

    return None

@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(req: PasswordResetRequest, request: Request):
    ip = request.client.host if request.client else "127.0.0.1"
    email_clean = req.email.strip().lower()

    # Rate limiting: max 3 reset requests per hour per email
    rate_key = f"rate:reset:{email_clean}"
    attempts = redis_client.incr(rate_key)
    if attempts == 1:
        redis_client.expire(rate_key, 3600)
    if attempts > 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много запросов восстановления. Попробуйте позже."
        )

    import secrets
    # Generate 6-digit one-time code
    reset_code = f"{secrets.randbelow(1000000):06d}"

    with pool.connection() as conn:
        user_row = conn.execute(
            "SELECT id FROM users WHERE lower(email) = %s AND is_active = TRUE",
            (email_clean,)
        ).fetchone()

    # Always return 202 Accepted even if user not found (to prevent user enumeration)
    if user_row:
        user_id = str(user_row["id"])
        # Save code in Redis with TTL (e.g. 15 mins)
        redis_client.setex(f"reset_code:{email_clean}", config.PASSWORD_RESET_TTL, reset_code)

        # Dispatch notification task to worker to send email to Mailpit
        publish("notifications", {
            "task": "send_email",
            "to_email": email_clean,
            "subject": "Восстановление доступа",
            "body": f"Ваш одноразовый код для смены пароля: {reset_code}. Код действителен {config.PASSWORD_RESET_TTL // 60} минут."
        })

        publish("audit", {
            "actor_user_id": user_id,
            "action": "auth.password_reset.requested",
            "entity_type": "user",
            "entity_id": user_id,
            "details": {"email": email_clean},
            "ip_address": ip,
        })
    else:
        publish("audit", {
            "actor_user_id": None,
            "action": "auth.password_reset.requested_nonexistent",
            "entity_type": "user",
            "entity_id": None,
            "details": {"email": email_clean},
            "ip_address": ip,
        })

    return {"message": "Если пользователь с таким email существует, на почту отправлены инструкции."}

@router.post("/password-reset/confirm", status_code=status.HTTP_200_OK)
def confirm_password_reset(req: PasswordResetConfirmRequest, request: Request):
    ip = request.client.host if request.client else "127.0.0.1"
    email_clean = req.email.strip().lower()

    # Verify one-time code from Redis
    cached_code = redis_client.get(f"reset_code:{email_clean}")

    invalid_exc = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Недействительный или истёкший код восстановления"
    )

    if not cached_code or cached_code != req.reset_code:
        raise invalid_exc

    from ..security import hash_password
    pwd_hash, pwd_salt = hash_password(req.new_password, config.PASSWORD_PEPPER)

    with pool.connection() as conn:
        user_row = conn.execute(
            """UPDATE users
               SET password_hash = %s, password_salt = %s, password_changed_at = CURRENT_TIMESTAMP
               WHERE lower(email) = %s AND is_active = TRUE
               RETURNING id""",
            (pwd_hash, pwd_salt, email_clean)
        ).fetchone()

        if not user_row:
            raise invalid_exc
        conn.commit()

    # Code works only once -> delete immediately
    redis_client.delete(f"reset_code:{email_clean}")

    publish("audit", {
        "actor_user_id": str(user_row["id"]),
        "action": "auth.password_reset.completed",
        "entity_type": "user",
        "entity_id": str(user_row["id"]),
        "details": {"email": email_clean},
        "ip_address": ip,
    })

    return {"message": "Пароль успешно изменён."}

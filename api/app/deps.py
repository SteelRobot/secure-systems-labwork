from fastapi import Header, HTTPException, status
import jwt
from typing import Annotated

from . import config
from .cache import r as redis_client

class CurrentUser:
    def __init__(self, user_id: str, role: str, department_id: str | None, jti: str):
        self.id = user_id
        self.role = role
        self.department_id = department_id
        self.jti = jti

def get_current_user(authorization: Annotated[str | None, Header()] = None) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходима аутентификация (Bearer токен)"
        )

    token = authorization[7:].strip()
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен истек")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not jti or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Некорректный состав токена")

    # Проверка наличия активной сессии в Redis (позволяет выполнять честный logout/отзыв)
    session_user_id = redis_client.get(f"session:{jti}")
    if not session_user_id or session_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия отозвана или истекла")

    return CurrentUser(
        user_id=user_id,
        role=payload.get("role", ""),
        department_id=payload.get("department_id"),
        jti=jti
    )

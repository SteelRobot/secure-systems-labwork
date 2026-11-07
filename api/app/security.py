"""Хеширование паролей: HMAC-SHA256(перец, пароль) -> Argon2id с индивидуальной солью.
Перец – из окружения, соль – в users.password_salt, хеш – в users.password_hash."""
import hashlib
import hmac
import secrets

from argon2 import Type
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from argon2.low_level import hash_secret, verify_secret

# Параметры стоимости Argon2id (рекомендация OWASP: m>=19 MiB, t>=2, p=1)
_T, _M, _P = 3, 19456, 1


def _prehash(password: str, pepper: str) -> bytes:
    return hmac.new(pepper.encode(), password.encode(), hashlib.sha256).digest()


def hash_password(password: str, pepper: str) -> tuple[str, str]:
    """Возвращает (password_hash, password_salt)."""
    salt = secrets.token_bytes(16)
    encoded = hash_secret(_prehash(password, pepper), salt, time_cost=_T,
                          memory_cost=_M, parallelism=_P, hash_len=32, type=Type.ID)
    return encoded.decode(), salt.hex()


def verify_password(password: str, password_hash: str, pepper: str) -> bool:
    try:
        return verify_secret(password_hash.encode(), _prehash(password, pepper), Type.ID)
    except (VerifyMismatchError, InvalidHashError):
        return False

"""Redis: сессии (jti), ограничение частоты, ключи идемпотентности, коды сброса пароля."""
import redis

from . import config

r = redis.Redis(host=config.REDIS_HOST, password=config.REDIS_PASSWORD, decode_responses=True)

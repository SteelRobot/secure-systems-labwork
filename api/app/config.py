"""Все настройки читаются из окружения. Значений по умолчанию для секретов нет:
если переменной нет, сервис не стартует (KeyError)."""
import os

DB_HOST = os.environ["DB_HOST"]
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]

REDIS_HOST = os.environ["REDIS_HOST"]
REDIS_PASSWORD = os.environ["REDIS_PASSWORD"]

BROKER_HOST = os.environ["BROKER_HOST"]
BROKER_USER = os.environ["BROKER_USER"]
BROKER_PASSWORD = os.environ["BROKER_PASSWORD"]

STORAGE_ENDPOINT = os.environ["STORAGE_ENDPOINT"]
STORAGE_ACCESS_KEY = os.environ["STORAGE_ACCESS_KEY"]
STORAGE_SECRET_KEY = os.environ["STORAGE_SECRET_KEY"]
STORAGE_BUCKET = "documents"

JWT_SECRET = os.environ["JWT_SECRET"]
PASSWORD_PEPPER = os.environ["PASSWORD_PEPPER"]
ACCESS_TOKEN_TTL = int(os.environ["ACCESS_TOKEN_TTL_SECONDS"])
PASSWORD_RESET_TTL = int(os.environ["PASSWORD_RESET_TTL_SECONDS"])

API_DOCS_ENABLED = os.environ.get("API_DOCS_ENABLED", "false").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

"""Пул соединений PostgreSQL. Подключение – под ролью app_api (не postgres).
Запросы только параметризованные: значения передаются вторым аргументом execute()."""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

pool = ConnectionPool(
    conninfo=f"host={config.DB_HOST} dbname={config.DB_NAME} user={config.DB_USER} password={config.DB_PASSWORD}",
    min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=False,
)

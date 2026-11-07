#!/bin/bash
# Обёртка: передаёт пароли ролей из окружения контейнера в roles.sql
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v api_password="$DB_API_PASSWORD" \
     -v worker_password="$DB_WORKER_PASSWORD" \
     -f /sql/roles.sql

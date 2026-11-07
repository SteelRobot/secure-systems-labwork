#!/usr/bin/env bash
# Создаёт .env со случайными секретами на основе .env.example.
# Существующий непустой .env не трогает (для пересоздания удалите его).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -s .env ]; then echo ".env уже существует – ничего не сделано"; exit 0; fi
rnd() { head -c 96 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "$1"; }
declare -A V=(
  [POSTGRES_PASSWORD]="$(rnd 32)" [DB_API_PASSWORD]="$(rnd 32)" [DB_WORKER_PASSWORD]="$(rnd 32)"
  [REDIS_PASSWORD]="$(rnd 32)" [RABBITMQ_PASSWORD]="$(rnd 32)"
  [STORAGE_ACCESS_KEY]="$(rnd 20)" [STORAGE_SECRET_KEY]="$(rnd 40)"
  [JWT_SECRET]="$(rnd 64)" [PASSWORD_PEPPER]="$(rnd 48)"
  [FINANCE_API_TOKEN]="$(rnd 32)" [MONITORING_API_TOKEN]="$(rnd 32)"
  [SEED_PASSWORD]="Demo-Passw0rd"
)
while IFS= read -r line; do
  if [[ "$line" =~ ^([A-Z_]+)=$ ]] && [[ -n "${V[${BASH_REMATCH[1]}]:-}" ]]; then
    echo "${BASH_REMATCH[1]}=${V[${BASH_REMATCH[1]}]}"
  else
    echo "$line"
  fi
done < .env.example > .env
chmod 600 .env
echo ".env создан"

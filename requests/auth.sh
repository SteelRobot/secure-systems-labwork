#!/usr/bin/env bash
set -euo pipefail
BASE_URL="https://localhost:8443"

echo "=== 1. Успешный вход (Заявитель) ==="
curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}'
echo -e "
"

echo "=== 2. Успешный вход (Ответственный сотрудник) ==="
curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "employee1@univ.local", "password": "Demo-Passw0rd"}'
echo -e "
"

echo "=== 3. Неверный пароль (401) ==="
curl -sk -i -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "WrongPassword"}'
echo -e "
"

echo "=== 4. Несуществующий пользователь (401) ==="
curl -sk -i -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "nonexistent@univ.local", "password": "Demo-Passw0rd"}'
echo -e "
"

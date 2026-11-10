#!/usr/bin/env bash
# Проверка эндпоинта POST /api/applications/{id}/completeness-check
set -euo pipefail

BASE_URL="https://localhost:8443"

echo "=== 1. Логин Заявителя 1 ==="
AP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "=== 2. Создание заявки (draft) ==="
APP_JSON=$(curl -sk -X POST "$BASE_URL/api/applications" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AP1_TOKEN" \
  -d '{"support_type": "material_support", "academic_year": 2026, "comment": "Проверка ИИ"}')
APP_ID=$(echo "$APP_JSON" | grep -o '"id":"[^"]*' | cut -d'"' -f4)

echo "=== 3. Запуск ИИ-проверки (POST /api/applications/$APP_ID/completeness-check) ==="
CHECK_RESP=$(curl -sk -X POST "$BASE_URL/api/applications/$APP_ID/completeness-check" \
  -H "Authorization: Bearer $AP1_TOKEN")
echo "$CHECK_RESP"
echo -e "
"

echo "=== 4. Ожидание обработки воркером (2 сек) ==="
sleep 2

echo "=== 5. Получение результатов проверки (GET /api/applications/$APP_ID/completeness-check) ==="
curl -sk -X GET "$BASE_URL/api/applications/$APP_ID/completeness-check" \
  -H "Authorization: Bearer $AP1_TOKEN"
echo -e "
"

#!/usr/bin/env bash
set -euo pipefail
BASE_URL="https://localhost:8443"

echo "=== 1. Логин Заявителя 1 ==="
AP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "=== 2. Создание заявки в статусе draft (applicant1) ==="
APP_JSON=$(curl -sk -X POST "$BASE_URL/api/applications" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AP1_TOKEN" \
  -H "Idempotency-Key: test-key-100" \
  -d '{
    "support_type": "material_support",
    "academic_year": 2026,
    "requested_amount": 15000,
    "comment": "Заявка на материальную помощь"
  }')

echo "$APP_JSON"
APP_ID=$(echo "$APP_JSON" | grep -o '"id":"[^"]*' | cut -d'"' -f4)
echo "Создана заявка ID: $APP_ID"
echo -e "
"

echo "=== 3. Чтение своей заявки (applicant1) ==="
curl -sk -X GET "$BASE_URL/api/applications/$APP_ID" \
  -H "Authorization: Bearer $AP1_TOKEN"
echo -e "
"

echo "=== 4. Попытка Заявителя 2 прочитать чужую заявку (404) ==="
AP2_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant2@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

curl -sk -i -X GET "$BASE_URL/api/applications/$APP_ID" \
  -H "Authorization: Bearer $AP2_TOKEN"
echo -e "
"

echo "=== 5. Попытка ответственного сотрудника создать заявку (403 Forbidden) ==="
EMP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "employee1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

curl -sk -i -X POST "$BASE_URL/api/applications" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EMP1_TOKEN" \
  -d '{
    "support_type": "material_support",
    "academic_year": 2026,
    "comment": "Тест"
  }'
echo -e "
"

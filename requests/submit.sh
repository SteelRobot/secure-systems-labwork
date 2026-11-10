#!/usr/bin/env bash
# Проверка эндпоинта PATCH /api/applications/{id}/submit
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
  -d '{"support_type": "material_support", "academic_year": 2026, "comment": "Заявка на отправку"}')
APP_ID=$(echo "$APP_JSON" | grep -o '"id":"[^"]*' | cut -d'"' -f4)

echo "=== 3. Отправка заявки (PATCH /api/applications/$APP_ID/submit) ==="
curl -sk -X PATCH "$BASE_URL/api/applications/$APP_ID/submit" \
  -H "Authorization: Bearer $AP1_TOKEN" \
  -H "Idempotency-Key: submit-key-1"
echo -e "
"

echo "=== 4. Повторная отправка уже отправленной заявки (409 Conflict) ==="
curl -sk -i -X PATCH "$BASE_URL/api/applications/$APP_ID/submit" \
  -H "Authorization: Bearer $AP1_TOKEN"
echo -e "
"

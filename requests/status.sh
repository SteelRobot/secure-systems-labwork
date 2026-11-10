#!/usr/bin/env bash
# Проверка эндпоинта PATCH /api/applications/{id}/status
set -euo pipefail

BASE_URL="https://localhost:8443"

echo "=== 1. Логин Заявителя 1 и Ответственного сотрудника ==="
AP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

EMP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "employee1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "=== 2. Заявитель создаёт и отправляет заявку ==="
APP_JSON=$(curl -sk -X POST "$BASE_URL/api/applications" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AP1_TOKEN" \
  -d '{"support_type": "material_support", "academic_year": 2026, "requested_amount": 10000, "comment": "На рассмотрение"}')
APP_ID=$(echo "$APP_JSON" | grep -o '"id":"[^"]*' | cut -d'"' -f4)

curl -sk -X PATCH "$BASE_URL/api/applications/$APP_ID/submit" -H "Authorization: Bearer $AP1_TOKEN" > /dev/null

echo "=== 3. Сотрудник переводит заявку в под статус 'under_review' ==="
curl -sk -X PATCH "$BASE_URL/api/applications/$APP_ID/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EMP1_TOKEN" \
  -d '{"status": "under_review", "decision_comment": "Взято в работу"}'
echo -e "
"

echo "=== 4. Сотрудник одобряет заявку ('approved') с указанием суммы ==="
curl -sk -X PATCH "$BASE_URL/api/applications/$APP_ID/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EMP1_TOKEN" \
  -d '{"status": "approved", "approved_amount": 10000, "decision_comment": "Документы подтверждены"}'
echo -e "
"

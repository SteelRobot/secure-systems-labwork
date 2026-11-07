#!/usr/bin/env bash
set -euo pipefail
BASE_URL="https://localhost:8443"

echo "=== 1. Логин Заявителя 1 ==="
AP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "=== 2. Заявитель 1 создаёт черновик ==="
DRAFT_JSON=$(curl -sk -X POST "$BASE_URL/api/applications" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AP1_TOKEN" \
  -d '{
    "support_type": "material_support",
    "academic_year": 2026,
    "comment": "Секретный черновик заявителя"
  }')

DRAFT_ID=$(echo "$DRAFT_JSON" | grep -o '"id":"[^"]*' | cut -d'"' -f4)
echo "Создан черновик ID: $DRAFT_ID"

echo "=== 3. Логин Ответственного сотрудника (employee1) ==="
EMP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "employee1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "=== 4. Запрос черновика сотрудником по ID (404 Not Found) ==="
curl -sk -i -X GET "$BASE_URL/api/applications/$DRAFT_ID" \
  -H "Authorization: Bearer $EMP1_TOKEN"
echo -e "
"

echo "=== 5. Попытка сотрудника фильтровать по draft ==="
curl -sk -X GET "$BASE_URL/api/applications?status_filter=draft" \
  -H "Authorization: Bearer $EMP1_TOKEN"
echo -e "
"

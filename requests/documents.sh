#!/usr/bin/env bash
# Проверка эндпоинта POST /api/applications/{id}/documents
set -euo pipefail

BASE_URL="https://localhost:8443"

echo "=== 1. Логин Заявителя 1 ==="
AP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "=== 2. Создание заявки в статусе draft ==="
APP_JSON=$(curl -sk -X POST "$BASE_URL/api/applications" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AP1_TOKEN" \
  -d '{
    "support_type": "material_support",
    "academic_year": 2026,
    "comment": "Заявка с документом"
  }')
APP_ID=$(echo "$APP_JSON" | grep -o '"id":"[^"]*' | cut -d'"' -f4)

echo "=== 3. Создание тестового PDF файла ==="
TEST_FILE="/tmp/test_document.pdf"
echo "%PDF-1.4 тестовый документ основание" > "$TEST_FILE"

echo "=== 4. Загрузка документа к черновику заявки ==="
curl -sk -X POST "$BASE_URL/api/applications/$APP_ID/documents" \
  -H "Authorization: Bearer $AP1_TOKEN" \
  -F "file=@$TEST_FILE;type=application/pdf"
echo -e "
"

echo "=== 5. Чтение детальной информации по заявке (должен появиться документ) ==="
curl -sk -X GET "$BASE_URL/api/applications/$APP_ID" \
  -H "Authorization: Bearer $AP1_TOKEN"
echo -e "
"

rm -f "$TEST_FILE"

#!/usr/bin/env bash
# Проверка формирования отчётов (GET /api/reports/applications)
set -euo pipefail

BASE_URL="https://localhost:8443"

echo "=== 1. Логин Ответственного сотрудника (employee1) ==="
EMP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "employee1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "=== 2. Запрос на формирование сводного отчёта (202 Accepted) ==="
REPORT_RESP=$(curl -sk -X GET "$BASE_URL/api/reports/applications" \
  -H "Authorization: Bearer $EMP1_TOKEN" \
  -H "Idempotency-Key: report-key-1")
echo "$REPORT_RESP"
REPORT_ID=$(echo "$REPORT_RESP" | grep -o '"report_id":"[^"]*' | cut -d'"' -f4)
echo "Идентификатор отчёта: $REPORT_ID"
echo -e "
"

echo "=== 3. Пауза 2 сек для обработки отчёта воркером ==="
sleep 2

echo "=== 4. Проверка статуса отчёта (GET /api/reports/$REPORT_ID) ==="
curl -sk -X GET "$BASE_URL/api/reports/$REPORT_ID" \
  -H "Authorization: Bearer $EMP1_TOKEN"
echo -e "
"

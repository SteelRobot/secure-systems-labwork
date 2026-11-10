#!/usr/bin/env bash
# Проверочный запрос 2 (Задание 7.2 ЛР №3):
# Создание объекта с лишними полями в теле (status: "approved", applicant_id: "чужой ID", approved_amount: 100000).
# Ожидаемый результат: Сервер полностью игнорирует присланные поля,
# устанавливает status="draft", applicant_id из токена, approved_amount=null.
set -euo pipefail

BASE_URL="https://localhost:8443"

AP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "Отправка запроса создания заявки с внедрёнными лишними полями (status, applicant_id, approved_amount):"
curl -sk -X POST "$BASE_URL/api/applications" \
  -H "Authorization: Bearer $AP1_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "support_type": "material_support",
    "academic_year": 2026,
    "comment": "Попытка взлома полей",
    "status": "approved",
    "applicant_id": "00000000-0000-0000-0000-000000000000",
    "approved_amount": 999999
  }'
echo -e "
"

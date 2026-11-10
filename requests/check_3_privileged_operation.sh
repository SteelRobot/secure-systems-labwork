#!/usr/bin/env bash
# Проверочный запрос 3 (Задание 7.2 ЛР №3):
# Вызов привилегированной операции (формирование сводного отчёта GET /api/reports/applications)
# токеном обычного пользователя (Заявителя), минуя веб-интерфейс.
# Ожидаемый результат: HTTP 403 Forbidden.
set -euo pipefail

BASE_URL="https://localhost:8443"

AP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "Вызов отчёта токеном Заявителя:"
curl -sk -i -X GET "$BASE_URL/api/reports/applications" \
  -H "Authorization: Bearer $AP1_TOKEN"

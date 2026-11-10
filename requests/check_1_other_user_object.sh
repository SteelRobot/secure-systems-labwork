#!/usr/bin/env bash
# Проверочный запрос 1 (Задание 7.2 ЛР №3):
# Запрос объекта другого пользователя с действительным токеном.
# Заявитель 2 пытается просмотреть заявку Заявителя 1.
# Ожидаемый результат: HTTP 404 Not Found (не раскрывает факт существования объекта).
set -euo pipefail

BASE_URL="https://localhost:8443"

# Вход под Заявителем 1 и создание заявки
AP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

APP_JSON=$(curl -sk -X POST "$BASE_URL/api/applications" \
  -H "Authorization: Bearer $AP1_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"support_type": "material_support", "academic_year": 2026, "comment": "Заявка Заявителя 1"}')

APP_ID=$(echo "$APP_JSON" | grep -o '"id":"[^"]*' | cut -d'"' -f4)
echo "Создана заявка Заявителя 1, ID: $APP_ID"

# Вход под Заявителем 2
AP2_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant2@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "Попытка Заявителя 2 прочитать чужую заявку $APP_ID:"
curl -sk -i -X GET "$BASE_URL/api/applications/$APP_ID" \
  -H "Authorization: Bearer $AP2_TOKEN"

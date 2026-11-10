#!/usr/bin/env bash
# Проверка регистрации, выхода из системы и восстановления доступа
set -euo pipefail

BASE_URL="https://localhost:8443"
TEST_EMAIL="new_student@univ.edu"
TEST_PASS="New-Strong-Pass123"

echo "=== 1. Регистрация нового заявителя ==="
curl -sk -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "university_id": "S-9999",
    "full_name": "Новиков Артём Игоревич",
    "email": "'"$TEST_EMAIL"'",
    "password": "'"$TEST_PASS"'"
  }'
echo -e "
"

echo "=== 2. Вход под зарегистрированным пользователем ==="
LOGIN_RESP=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "'"$TEST_EMAIL"'", "password": "'"$TEST_PASS"'"}')
echo "$LOGIN_RESP"
TOKEN=$(echo "$LOGIN_RESP" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
echo -e "
"

echo "=== 3. Проверка успешности токена (получение списка заявок) ==="
curl -sk -X GET "$BASE_URL/api/applications" -H "Authorization: Bearer $TOKEN"
echo -e "
"

echo "=== 4. Выход из системы (POST /api/auth/logout) ==="
curl -sk -i -X POST "$BASE_URL/api/auth/logout" -H "Authorization: Bearer $TOKEN"
echo -e "
"

echo "=== 5. Попытка запроса с отозванным токеном (должна быть 401) ==="
curl -sk -i -X GET "$BASE_URL/api/applications" -H "Authorization: Bearer $TOKEN"
echo -e "
"

echo "=== 6. Запрос восстановления доступа (POST /api/auth/password-reset) ==="
curl -sk -X POST "$BASE_URL/api/auth/password-reset" \
  -H "Content-Type: application/json" \
  -d '{"email": "'"$TEST_EMAIL"'"}'
echo -e "
"

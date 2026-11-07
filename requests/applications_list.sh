#!/usr/bin/env bash
set -euo pipefail
BASE_URL="https://localhost:8443"

echo "=== 1. Логин Заявителя 1 ==="
AP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "applicant1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "=== 2. Список заявок Заявителя 1 ==="
curl -sk -X GET "$BASE_URL/api/applications" \
  -H "Authorization: Bearer $AP1_TOKEN"
echo -e "
"

echo "=== 3. Логин Ответственного сотрудника (employee1) ==="
EMP1_TOKEN=$(curl -sk -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "employee1@univ.local", "password": "Demo-Passw0rd"}' | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo "=== 4. Ответственный сотрудник видит заявки своего подразделения (кроме черновиков) ==="
curl -sk -X GET "$BASE_URL/api/applications" \
  -H "Authorization: Bearer $EMP1_TOKEN"
echo -e "
"

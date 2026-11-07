# Система приёма заявок на материальную поддержку (ЛР №3)

## Запуск
```bash
./scripts/init-env.sh        # создаёт .env со случайными секретами
docker compose up -d --build
```
Остановка: `docker compose down`. Сброс базы в исходное состояние: `docker compose down -v && docker compose up -d --build`.

## Адреса
| Сервис | Адрес |
|---|---|
| Веб-клиент (HTTPS, самоподписанный сертификат) | https://localhost:8443 |
| RabbitMQ консоль | http://localhost:15672 (логин/пароль из `.env`) |
| Mailpit (письма) | http://localhost:8025 |

## Тестовые учётные записи (пароль – `SEED_PASSWORD` из `.env`)
| Email | Роль | Подразделение |
|---|---|---|
| student1@univ.local, student2@univ.local | student | Институт компьютерных наук |
| employee1@univ.local | employee | Институт компьютерных наук |
| admin1@univ.local | service_admin (ответственный сотрудник) | Институт компьютерных наук |
| admin2@univ.local | service_admin | Институт машиностроения |
| tech@univ.local | technical_admin | – |

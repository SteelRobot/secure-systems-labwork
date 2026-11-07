#!/bin/sh
# Подставляет пользователя приложения из окружения в определения (очереди, обменники, права)
# и запускает RabbitMQ. Пароль в репозитории не хранится.
set -eu
sed -e "s/__USER__/$RABBITMQ_DEFAULT_USER/g" -e "s/__PASS__/$RABBITMQ_DEFAULT_PASS/g" \
    /etc/rabbitmq/definitions.template.json > /tmp/definitions.json
exec docker-entrypoint.sh rabbitmq-server

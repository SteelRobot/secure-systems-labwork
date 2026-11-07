-- Учётные записи приложения (п. 3.5 ЛР №2, задание 2.2 ЛР №3).
-- Запускается один раз при инициализации БД через db/init-roles.sh,
-- пароли приходят из окружения как psql-переменные.
-- Принцип наименьших привилегий: роли не владеют таблицами, DDL запрещён.

CREATE ROLE app_api    LOGIN PASSWORD :'api_password'    NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE app_worker LOGIN PASSWORD :'worker_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Схема public: никаких CREATE для всех, только USAGE для наших ролей
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_api, app_worker;

-- ---------- backend API (app_api) ----------
GRANT SELECT ON departments TO app_api;
GRANT SELECT ON users TO app_api;
-- единственное, что API меняет в users – данные пароля (восстановление доступа)
GRANT UPDATE (password_hash, password_salt, password_changed_at) ON users TO app_api;
GRANT SELECT, INSERT, UPDATE ON applications TO app_api;
GRANT SELECT, INSERT ON documents TO app_api;
GRANT SELECT ON llm_checks TO app_api;
-- audit_log API не видит и не пишет: события уходят в брокер, пишет worker

-- ---------- worker (app_worker) ----------
GRANT SELECT ON users, applications, documents TO app_worker;
-- заявки worker только читает (для сводных отчётов), менять их он не может
GRANT SELECT, INSERT ON audit_log TO app_worker;
GRANT USAGE ON SEQUENCE audit_log_id_seq TO app_worker;

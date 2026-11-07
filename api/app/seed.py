"""Тестовые данные. Запускается один раз контейнером db-seed под суперпользователем БД
(роль app_api не имеет прав на INSERT в users). Повторный запуск безопасен."""
import os

import psycopg

from .security import hash_password

PEPPER = os.environ["PASSWORD_PEPPER"]
PASSWORD = os.environ["SEED_PASSWORD"]

DEPARTMENTS = ["Институт компьютерных наук", "Институт машиностроения"]
# (university_id, ФИО, email, роль, подразделение)
USERS = [
    ("S-1001", "Иванов Иван Иванович", "student1@univ.local", "student", 0),
    ("S-1002", "Петрова Анна Сергеевна", "student2@univ.local", "student", 0),
    ("E-2001", "Сидоров Пётр Петрович", "employee1@univ.local", "employee", 0),
    ("A-3001", "Кузнецова Мария Олеговна", "admin1@univ.local", "service_admin", 0),
    ("A-3002", "Орлов Дмитрий Андреевич", "admin2@univ.local", "service_admin", 1),
    ("T-4001", "Тех Специалист", "tech@univ.local", "technical_admin", None),
]
# (email заявителя, тип, год, статус, сумма, комментарий)
APPLICATIONS = [
    ("student1@univ.local", "material_support", 2026, "draft", 5000, "Тяжёлое материальное положение"),
    ("student1@univ.local", "pgas", 2026, "submitted", 12000, "Научные достижения за год"),
    ("student2@univ.local", "material_support", 2026, "submitted", 7000, "Лечение родственника"),
    ("student2@univ.local", "state_academic_scholarship", 2025, "approved", None, "Отличная успеваемость"),
]


def main() -> None:
    with psycopg.connect(host=os.environ["DB_HOST"], dbname=os.environ["POSTGRES_DB"],
                         user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"]) as conn:
        dep_ids = []
        for name in DEPARTMENTS:
            conn.execute("INSERT INTO departments (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (name,))
            dep_ids.append(conn.execute("SELECT id FROM departments WHERE name = %s", (name,)).fetchone()[0])
        for uid, name, email, role, dep in USERS:
            h, s = hash_password(PASSWORD, PEPPER)
            conn.execute(
                """INSERT INTO users (university_id, full_name, email, role, password_hash, password_salt, department_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (email) DO NOTHING""",
                (uid, name, email, role, h, s, dep_ids[dep] if dep is not None else None))
        if conn.execute("SELECT count(*) FROM applications").fetchone()[0] == 0:
            for email, stype, year, status, amount, comment in APPLICATIONS:
                conn.execute(
                    """INSERT INTO applications (applicant_id, support_type, academic_year, status, requested_amount, comment, submitted_at)
                       VALUES ((SELECT id FROM users WHERE email=%s),%s,%s,%s,%s,%s,
                               CASE WHEN %s='draft' THEN NULL ELSE now() END)""",
                    (email, stype, year, status, amount, comment, status))
        conn.commit()
    print("seed: готово")


if __name__ == "__main__":
    main()

"""Apply the idempotent guest quota migration to the configured database.

Run from Verifai-backend: python -m scripts.migrate_guest_quotas
"""

from pathlib import Path

from app.Global.db import engine


def main():
    if engine.dialect.name != "postgresql":
        raise RuntimeError("The SQL migration targets PostgreSQL")
    sql = (Path(__file__).resolve().parents[1] / "migrations/003_guest_quotas.sql").read_text()
    with engine.connect() as connection:
        connection.exec_driver_sql(sql)
        connection.commit()
    print("Guest quota migration applied successfully.")


if __name__ == "__main__":
    main()

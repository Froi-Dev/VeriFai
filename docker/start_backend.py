"""Initialize a fresh local database and start the API. Fail closed on SQL errors."""
import os
from pathlib import Path

from app.Global.db import Base, engine
import app.Auth.models  # noqa: F401
import app.ContentDetector.guest_quota  # noqa: F401

Base.metadata.create_all(bind=engine)
# These migrations are idempotent. Exclude the manual least-privilege example.
with engine.connect() as connection:
    connection = connection.execution_options(isolation_level="AUTOCOMMIT")
    for filename in (
        "001_security_hardening.sql",
        "002_auth_session_resilience.sql",
        "003_guest_quotas.sql",
    ):
        connection.exec_driver_sql((Path("migrations") / filename).read_text())
engine.dispose()
os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"])

from app.Global.db import engine
from sqlalchemy import inspect

inspector = inspect(engine)
print("Foreign keys:", inspector.get_foreign_keys("scan_results", schema="public"))
print("Indexes:", inspector.get_indexes("scan_results", schema="public"))
print("PK:", inspector.get_pk_constraint("scan_results", schema="public"))

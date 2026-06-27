"""Vérifie l'état PGVector sur PostgreSQL."""
from sqlalchemy import text

from app.core.database import engine

with engine.connect() as conn:
    ver = conn.execute(text("SELECT version()")).scalar()
    print("PG:", (ver or "")[:100])
    avail = conn.execute(
        text("SELECT name, installed_version FROM pg_available_extensions WHERE name = 'vector'")
    ).fetchall()
    print("vector available:", avail)
    installed = conn.execute(
        text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
    ).fetchall()
    print("vector installed:", installed)

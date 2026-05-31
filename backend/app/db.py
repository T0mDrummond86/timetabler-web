"""PostgreSQL connection (tenancy tables added in Phase 1)."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def check_database() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

"""Persistent SQLite storage. Each timetabling session is its own .db file."""
from __future__ import annotations

import os
import re
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .models import Base, Semester, Week


DEFAULT_SESSION_NAME = "Default"


def app_data_dir() -> Path:
    """Mac/Linux/Windows app data dir for this app."""
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif os.uname().sysname == "Darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = root / "JoondalupTimetable"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sessions_dir() -> Path:
    d = app_data_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _migrate_legacy_db() -> None:
    """Move the pre-sessions single DB into sessions/Default.db on first run."""
    legacy = app_data_dir() / "timetable.db"
    target = sessions_dir() / f"{DEFAULT_SESSION_NAME}.db"
    if legacy.exists() and not target.exists():
        legacy.rename(target)


def db_path(session_name: str = DEFAULT_SESSION_NAME) -> Path:
    _migrate_legacy_db()
    return sessions_dir() / f"{_sanitise_session_name(session_name)}.db"


def list_sessions() -> list[str]:
    return sorted(p.stem for p in sessions_dir().glob("*.db"))


def _sanitise_session_name(name: str) -> str:
    """Strip filesystem-unsafe characters; collapse whitespace."""
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or "Untitled"


def rename_session(old_name: str, new_name: str) -> Path:
    src = db_path(old_name)
    dst = db_path(new_name)
    if not src.exists():
        raise FileNotFoundError(f"Session {old_name!r} does not exist")
    if dst.exists() and dst != src:
        raise FileExistsError(f"Session {new_name!r} already exists")
    src.rename(dst)
    return dst


def delete_session(name: str) -> None:
    p = db_path(name)
    if p.exists():
        p.unlink()


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def make_engine(path: Path | str | None = None, *, session_name: str | None = None) -> Engine:
    if path is not None:
        p = Path(path)
    elif session_name is not None:
        p = db_path(session_name)
    else:
        p = db_path()
    # NullPool: each session checkout gets a fresh SQLite connection and closes it
    # on return, so background solver threads do not fight the UI connection.
    return create_engine(
        f"sqlite:///{p}",
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=NullPool,
    )


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _apply_migrations(engine)
    # Ensure a default semester + week 0 exist so the UI has something to attach to.
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionLocal() as s:
        sem = s.query(Semester).first()
        if sem is None:
            sem = Semester(name="Semester 2, 2026", num_weeks=18, repeating=1)
            s.add(sem)
            s.flush()
            s.add(Week(semester_id=sem.id, week_number=0, label="Repeating week"))
            s.commit()


def _apply_migrations(engine: Engine) -> None:
    """Apply pending schema migrations from the registry."""
    from .migrations import apply_migrations
    apply_migrations(engine)


def open_session(engine: Engine | None = None, *, session_name: str | None = None) -> Session:
    eng = engine or make_engine(session_name=session_name)
    init_db(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()

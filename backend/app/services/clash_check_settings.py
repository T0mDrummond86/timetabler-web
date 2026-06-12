"""Load and persist per-session clash check toggles."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.clash_check_settings import (
    clash_settings_rows,
    default_clash_check_enabled,
    load_clash_check_settings,
    parse_clash_check_settings_json,
    save_clash_check_settings,
)
from timetable.core.tenancy_models import TimetableSession

from .violation_cache import invalidate_session_violations


def get_session_clash_settings(db: Session, timetable_session_id: int) -> dict[str, bool]:
    row = db.get(TimetableSession, timetable_session_id)
    if row is None:
        raise LookupError("Session not found")
    return load_clash_check_settings(row)


def list_clash_settings_for_api(db: Session, timetable_session_id: int) -> list[dict]:
    settings = get_session_clash_settings(db, timetable_session_id)
    return clash_settings_rows(settings)


def patch_clash_settings(
    db: Session,
    timetable_session_id: int,
    updates: dict[str, bool],
) -> list[dict]:
    row = db.get(TimetableSession, timetable_session_id)
    if row is None:
        raise LookupError("Session not found")
    current = parse_clash_check_settings_json(row.clash_check_settings_json)
    for code, enabled in updates.items():
        if code in current:
            current[code] = bool(enabled)
    save_clash_check_settings(row, current)
    invalidate_session_violations(db, timetable_session_id)
    return clash_settings_rows(current)


def reset_clash_settings(db: Session, timetable_session_id: int) -> list[dict]:
    row = db.get(TimetableSession, timetable_session_id)
    if row is None:
        raise LookupError("Session not found")
    defaults = default_clash_check_enabled()
    save_clash_check_settings(row, defaults)
    invalidate_session_violations(db, timetable_session_id)
    return clash_settings_rows(defaults)

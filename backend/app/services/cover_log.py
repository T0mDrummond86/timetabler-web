"""Cover log: persistent one-off cover jobs scoped to a global session."""
from __future__ import annotations

import datetime as _dt

from sqlalchemy.orm import Session

from timetable.core.tenancy_models import CoverLogEntry
from timetable.core.cover_hours import hours_from_time_label


def _entry_out(e: CoverLogEntry) -> dict:
    return {
        "id": e.id,
        "cover_date": e.cover_date.isoformat() if e.cover_date else None,
        "day_label": e.day_label,
        "time_label": e.time_label,
        "group_name": e.group_name,
        "unit_name": e.unit_name,
        "room_code": e.room_code,
        "away_staff_name": e.away_staff_name,
        "cover_staff_name": e.cover_staff_name,
        "source_session_name": e.source_session_name,
        "hours": e.hours,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def list_cover_log_entries(db: Session, *, global_session_id: int) -> list[dict]:
    rows = (
        db.query(CoverLogEntry)
        .filter(CoverLogEntry.global_session_id == global_session_id)
        .order_by(CoverLogEntry.cover_date.desc(), CoverLogEntry.created_at.desc())
        .all()
    )
    return [_entry_out(e) for e in rows]


def create_cover_log_entry(
    db: Session,
    *,
    global_session_id: int,
    cover_date: str,
    day_label: str,
    time_label: str,
    group_name: str,
    unit_name: str,
    room_code: str,
    away_staff_name: str,
    cover_staff_name: str,
    source_session_name: str,
    hours: float | None = None,
) -> dict:
    try:
        parsed_date = _dt.date.fromisoformat(cover_date)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid cover date") from exc

    # Prefer the exact figure from the booking; the label is only a fallback
    # for callers that no longer have the booking to hand.
    if hours is None:
        hours = hours_from_time_label(time_label)

    entry = CoverLogEntry(
        global_session_id=global_session_id,
        hours=hours,
        cover_date=parsed_date,
        day_label=day_label or "",
        time_label=time_label or "",
        group_name=group_name or "",
        unit_name=unit_name or "",
        room_code=room_code or "",
        away_staff_name=away_staff_name or "",
        cover_staff_name=cover_staff_name or "",
        source_session_name=source_session_name or "",
    )
    db.add(entry)
    db.flush()
    db.commit()
    return _entry_out(entry)


def delete_cover_log_entry(db: Session, *, global_session_id: int, entry_id: int) -> None:
    entry = db.get(CoverLogEntry, entry_id)
    if entry is None or entry.global_session_id != global_session_id:
        raise LookupError("Cover log entry not found")
    db.delete(entry)
    db.commit()

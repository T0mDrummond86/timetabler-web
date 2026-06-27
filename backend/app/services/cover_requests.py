"""Pending cover requests staged in a session's lecturer-cover tab.

These persist the in-progress cover (created → emailed → awaiting reply) so they
survive reloads and stay editable. Pushing a request to the global cover log
creates a CoverLogEntry and deletes the request.
"""
from __future__ import annotations

import datetime as _dt

from sqlalchemy.orm import Session

from timetable.core.tenancy_models import CoverRequest

from .cover_log import create_cover_log_entry
from .global_sessions import global_session_for_timetable


def _parse_date(value: str | None) -> _dt.date | None:
    if not value:
        return None
    try:
        return _dt.date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid cover date") from exc


def _out(r: CoverRequest) -> dict:
    return {
        "id": r.id,
        "booking_id": r.booking_id,
        "cover_date": r.cover_date.isoformat() if r.cover_date else None,
        "semester": r.semester,
        "week_number": r.week_number,
        "day_label": r.day_label,
        "time_label": r.time_label,
        "qualification_name": r.qualification_name,
        "unit_name": r.unit_name,
        "room_code": r.room_code,
        "away_staff_name": r.away_staff_name,
        "cover_staff_id": r.cover_staff_id,
        "cover_staff_name": r.cover_staff_name,
    }


def list_cover_requests(db: Session, *, timetable_session_id: int) -> list[dict]:
    rows = (
        db.query(CoverRequest)
        .filter(CoverRequest.timetable_session_id == timetable_session_id)
        .order_by(CoverRequest.created_at)
        .all()
    )
    return [_out(r) for r in rows]


def create_cover_request(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int | None,
    cover_date: str | None,
    semester: int | None,
    week_number: int | None,
    day_label: str,
    time_label: str,
    qualification_name: str,
    unit_name: str,
    room_code: str,
    away_staff_name: str,
    cover_staff_id: int | None,
    cover_staff_name: str,
) -> dict:
    # One request per booking: update in place if the class already has one.
    existing = None
    if booking_id is not None:
        existing = (
            db.query(CoverRequest)
            .filter(
                CoverRequest.timetable_session_id == timetable_session_id,
                CoverRequest.booking_id == booking_id,
            )
            .first()
        )
    parsed = _parse_date(cover_date)
    if existing is not None:
        existing.cover_date = parsed
        existing.semester = semester
        existing.week_number = week_number
        existing.day_label = day_label or ""
        existing.time_label = time_label or ""
        existing.qualification_name = qualification_name or ""
        existing.unit_name = unit_name or ""
        existing.room_code = room_code or ""
        existing.away_staff_name = away_staff_name or ""
        existing.cover_staff_id = cover_staff_id
        existing.cover_staff_name = cover_staff_name or ""
        db.flush()
        db.commit()
        return _out(existing)

    row = CoverRequest(
        timetable_session_id=timetable_session_id,
        booking_id=booking_id,
        cover_date=parsed,
        semester=semester,
        week_number=week_number,
        day_label=day_label or "",
        time_label=time_label or "",
        qualification_name=qualification_name or "",
        unit_name=unit_name or "",
        room_code=room_code or "",
        away_staff_name=away_staff_name or "",
        cover_staff_id=cover_staff_id,
        cover_staff_name=cover_staff_name or "",
    )
    db.add(row)
    db.flush()
    db.commit()
    return _out(row)


def _get(db: Session, timetable_session_id: int, request_id: int) -> CoverRequest:
    row = db.get(CoverRequest, request_id)
    if row is None or row.timetable_session_id != timetable_session_id:
        raise LookupError("Cover request not found")
    return row


def update_cover_request(
    db: Session,
    *,
    timetable_session_id: int,
    request_id: int,
    cover_staff_id: int | None = None,
    cover_staff_name: str | None = None,
    cover_date: str | None = None,
) -> dict:
    row = _get(db, timetable_session_id, request_id)
    if cover_staff_id is not None or cover_staff_name is not None:
        row.cover_staff_id = cover_staff_id
        row.cover_staff_name = cover_staff_name or ""
    if cover_date is not None:
        row.cover_date = _parse_date(cover_date)
    db.flush()
    db.commit()
    return _out(row)


def delete_cover_request(db: Session, *, timetable_session_id: int, request_id: int) -> None:
    row = _get(db, timetable_session_id, request_id)
    db.delete(row)
    db.commit()


def promote_cover_request(db: Session, *, timetable_session_id: int, request_id: int) -> dict:
    """Log an accepted request to the global cover log and remove it locally."""
    row = _get(db, timetable_session_id, request_id)
    gs = global_session_for_timetable(db, timetable_session_id)
    if gs is None:
        raise ValueError("This session is not part of a global group")
    if not row.cover_date:
        raise ValueError("Set a cover date before pushing to the global log")

    from .export_filenames import timetable_session_name

    entry = create_cover_log_entry(
        db,
        global_session_id=gs.id,
        cover_date=row.cover_date.isoformat(),
        day_label=row.day_label,
        time_label=row.time_label,
        qualification_name=row.qualification_name,
        unit_name=row.unit_name,
        room_code=row.room_code,
        away_staff_name=row.away_staff_name,
        cover_staff_name=row.cover_staff_name,
        source_session_name=timetable_session_name(db, timetable_session_id),
    )
    db.delete(row)
    db.commit()
    return {"logged": entry}

"""Pending cover requests staged in a session's lecturer-cover tab.

These persist the in-progress cover (created → emailed → awaiting reply) so they
survive reloads and stay editable. Pushing a request to the global cover log
creates a CoverLogEntry and deletes the request.
"""
from __future__ import annotations

import datetime as _dt

from sqlalchemy.orm import Session

from timetable.core.models import Booking
from timetable.core.tenancy_models import CoverRequest

from .cover_log import create_cover_log_entry
from .global_sessions import global_session_for_timetable
from timetable.core.cover_hours import hours_from_slots


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
        "group_name": r.group_name,
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
    return _with_ledger(db, timetable_session_id=timetable_session_id, rows=rows)


def _with_ledger(
    db: Session, *, timetable_session_id: int, rows: list[CoverRequest]
) -> list[dict]:
    """Attach each request's length and its effect on the cover lecturer's debt.

    The point of the pair is to answer "will this clear what they are owed?"
    while the plan is still being built. ``hours_owed_after`` runs cumulatively
    down the list, so giving one lecturer three covers shows the debt coming
    down three times rather than the same figure repeated.
    """
    from .cover_lecturers import _shortfall_by_lecturer

    owed = _shortfall_by_lecturer(db, timetable_session_id)
    running: dict[str, float] = {}
    out: list[dict] = []
    for r in rows:
        item = _out(r)
        booking = db.get(Booking, r.booking_id) if r.booking_id else None
        hours = hours_from_slots(booking.start_slot, booking.end_slot) if booking else None
        item["hours"] = hours

        key = (r.cover_staff_name or "").strip().casefold()
        before = owed.get(key)
        if not key or before is None:
            # Nobody assigned yet, or they are not behind — no debt to show.
            item["hours_owed_before"] = None
            item["hours_owed_after"] = None
        else:
            already = running.get(key, 0.0)
            item["hours_owed_before"] = round(max(0.0, before - already), 2)
            spent = already + (hours or 0.0)
            running[key] = spent
            item["hours_owed_after"] = round(max(0.0, before - spent), 2)
        out.append(item)
    return out


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
    group_name: str,
    unit_name: str,
    room_code: str,
    away_staff_name: str,
    cover_staff_id: int | None,
    cover_staff_name: str,
) -> dict:
    parsed = _parse_date(cover_date)
    # One request per (class, week): re-assigning the same week updates in place,
    # but a different week gets its own row so the same class can have different
    # cover in different weeks. The date is part of that identity, not just the
    # calendar's semester/week — without a calendar those are NULL, and the date
    # is then the only thing telling one week from the next.
    existing = None
    if booking_id is not None:
        existing = (
            db.query(CoverRequest)
            .filter(
                CoverRequest.timetable_session_id == timetable_session_id,
                CoverRequest.booking_id == booking_id,
                CoverRequest.semester == semester,
                CoverRequest.week_number == week_number,
                CoverRequest.cover_date == parsed,
            )
            .first()
        )
    if existing is not None:
        existing.cover_date = parsed
        existing.semester = semester
        existing.week_number = week_number
        existing.day_label = day_label or ""
        existing.time_label = time_label or ""
        existing.group_name = group_name or ""
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
        group_name=group_name or "",
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

    # Exact length from the slot grid when the booking is still there.
    booking = db.get(Booking, row.booking_id) if row.booking_id else None
    hours = (
        hours_from_slots(booking.start_slot, booking.end_slot) if booking else None
    )

    entry = create_cover_log_entry(
        db,
        hours=hours,
        global_session_id=gs.id,
        cover_date=row.cover_date.isoformat(),
        day_label=row.day_label,
        time_label=row.time_label,
        group_name=row.group_name,
        unit_name=row.unit_name,
        room_code=row.room_code,
        away_staff_name=row.away_staff_name,
        cover_staff_name=row.cover_staff_name,
        source_session_name=timetable_session_name(db, timetable_session_id),
    )
    db.delete(row)
    db.commit()
    return {"logged": entry}


def _monday_of(day: _dt.date) -> _dt.date:
    return day - _dt.timedelta(days=day.weekday())


def duplicate_latest_week(db: Session, *, timetable_session_id: int) -> dict:
    """Copy the last week of the pending cover plan forward by one week.

    The latest week rather than everything listed, so pressing the button twice
    gives week+1 then week+2. Copying the whole list each time would instead
    re-copy earlier weeks and multiply the plan.
    """
    rows = (
        db.query(CoverRequest)
        .filter(
            CoverRequest.timetable_session_id == timetable_session_id,
            CoverRequest.cover_date.isnot(None),
        )
        .all()
    )
    if not rows:
        raise ValueError(
            "Nothing to duplicate — cover requests need a date before they can be "
            "copied to another week."
        )

    monday = _monday_of(max(r.cover_date for r in rows))
    latest = [r for r in rows if _monday_of(r.cover_date) == monday]

    # Anything already sitting in the target week is left alone, so a second
    # press after a partial copy tops it up instead of duplicating rows.
    taken = {
        (r.booking_id, r.cover_date)
        for r in rows
        if _monday_of(r.cover_date) == monday + _dt.timedelta(days=7)
    }

    created = 0
    for r in latest:
        new_date = r.cover_date + _dt.timedelta(days=7)
        if (r.booking_id, new_date) in taken:
            continue
        db.add(
            CoverRequest(
                timetable_session_id=timetable_session_id,
                booking_id=r.booking_id,
                cover_date=new_date,
                semester=r.semester,
                # The calendar's own week numbering runs alongside the date; a
                # week further on is the next number when we have one.
                week_number=(r.week_number + 1) if r.week_number is not None else None,
                day_label=r.day_label,
                time_label=r.time_label,
                group_name=r.group_name,
                unit_name=r.unit_name,
                room_code=r.room_code,
                away_staff_name=r.away_staff_name,
                cover_staff_id=r.cover_staff_id,
                cover_staff_name=r.cover_staff_name,
            )
        )
        created += 1
    db.flush()
    db.commit()
    return {
        "created": created,
        "week_beginning": (monday + _dt.timedelta(days=7)).isoformat(),
        "copied_from_week_beginning": monday.isoformat(),
    }

"""Change log list, notes, manual records, rollback, and export."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from timetable.constants import DAYS
from timetable.core.booking_snapshots import _slot_to_str, snapshot_bookings
from timetable.core.change_log_data import (
    MANUAL_EDITABLE_ROW_KEYS,
    MANUAL_LOG_ACTION,
    gather_timetabling_change_log_display_rows,
    is_manual_change_log_entry,
    set_change_log_note,
)
from timetable.core.changelog import resolve_session_booking_net_maps
from timetable.core.models import Booking, ChangeLogEntry
from timetable.io.changelog_export import write_change_log_xlsx

from .booking_mutations import (
    BookingNotFoundError,
    _apply_snapshots,
    _booking_in_session,
    _mutation_result,
)


def list_change_log_rows(
    db: Session,
    *,
    timetable_session_id: int,
    resolved: bool,
) -> list[dict]:
    rows = gather_timetabling_change_log_display_rows(
        db,
        timetable_session_id=timetable_session_id,
        resolved=resolved,
    )
    return [
        {
            "when": r.when or None,
            "action": r.action,
            "booking_id": r.booking_id if r.booking_id >= 0 else None,
            "entry_id": r.entry_id,
            "note": r.note,
            "row": r.row,
        }
        for r in rows
    ]


def update_change_log_note(
    db: Session,
    *,
    timetable_session_id: int,
    entry_id: int,
    booking_id: int,
    note: str,
) -> None:
    entry = db.get(ChangeLogEntry, entry_id)
    if entry is None or entry.timetable_session_id != timetable_session_id:
        raise LookupError("Change log entry not found")
    set_change_log_note(
        db,
        timetable_session_id=timetable_session_id,
        entry_id=entry_id,
        booking_id=booking_id,
        note=note,
    )
    db.commit()


def create_manual_change_log_entry(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
) -> None:
    """Hand-written change record seeded from a placecard's current state.

    Logs a change that was actioned outside this session's tracking (e.g. on a
    previous version of the file). The lecturer/time/day/room fields start as
    the booking's current values and stay editable; the row always appears on
    the resolved log even though the tracked state shows no change.
    """
    booking = _booking_in_session(db, booking_id, timetable_session_id)
    row = {
        "id": (booking.external_id or "").strip(),
        "group": booking.course.code if booking.course else "",
        "class": booking.unit.name if booking.unit else "",
        "lecturer_change": booking.staff.name if booking.staff else "",
        "time_change": f"{_slot_to_str(booking.start_slot)}–{_slot_to_str(booking.end_slot)}",
        "day_change": DAYS[booking.day] if 0 <= booking.day < len(DAYS) else "",
        "room_change": booking.room.code if booking.room else "",
        "delete": "",
    }
    label = row["class"] or f"booking #{booking_id}"
    entry = ChangeLogEntry(
        timetable_session_id=timetable_session_id,
        action=MANUAL_LOG_ACTION,
        description=f"Manual change record — {label} ({row['group']})".strip(),
        # "seed" keeps the as-created values so exports can tell which fields
        # the user later edited (those are the ones highlighted red).
        details=json.dumps(
            {"manual": True, "booking_id": booking_id, "row": row, "seed": dict(row)}
        ),
    )
    db.add(entry)
    db.commit()


def _manual_entry(db: Session, timetable_session_id: int, entry_id: int) -> ChangeLogEntry:
    entry = db.get(ChangeLogEntry, entry_id)
    if (
        entry is None
        or entry.timetable_session_id != timetable_session_id
        or not is_manual_change_log_entry(entry)
    ):
        raise LookupError("Manual change-log entry not found")
    return entry


def update_manual_change_log_fields(
    db: Session,
    *,
    timetable_session_id: int,
    entry_id: int,
    fields: dict[str, str],
) -> None:
    """Edit the lecturer/time/day/room text of a manual record."""
    entry = _manual_entry(db, timetable_session_id, entry_id)
    payload = json.loads(entry.details or "{}")
    row = payload.get("row") or {}
    for key, value in fields.items():
        if key in MANUAL_EDITABLE_ROW_KEYS:
            row[key] = str(value or "").strip()
    payload["row"] = row
    entry.details = json.dumps(payload)
    db.commit()


def delete_manual_change_log_entry(
    db: Session,
    *,
    timetable_session_id: int,
    entry_id: int,
) -> None:
    """Remove a manual record. Refuses tracked (non-manual) entries."""
    entry = _manual_entry(db, timetable_session_id, entry_id)
    db.delete(entry)
    db.commit()


def rollback_booking_from_resolved(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
    course_id: int,
) -> dict:
    before_map, _after_map = resolve_session_booking_net_maps(
        db, timetable_session_id=timetable_session_id
    )
    target_state = before_map.get(booking_id)
    current_before = snapshot_bookings(db, [booking_id])
    if current_before.get(booking_id) == target_state:
        raise ValueError("Booking is already at the resolved rollback state")

    booking = db.get(Booking, booking_id)
    if booking is None and target_state is None:
        raise ValueError("Booking is already at the resolved rollback state")

    week = None
    if booking is not None:
        from timetable.core.models import Week

        week = db.get(Week, booking.week_id)
    elif target_state is not None:
        from timetable.core.models import Semester, Week

        sem = (
            db.query(Semester)
            .filter(Semester.timetable_session_id == timetable_session_id)
            .first()
        )
        if sem is None:
            raise BookingNotFoundError("Booking not found")
        week = (
            db.query(Week)
            .filter(Week.semester_id == sem.id, Week.week_number == 0)
            .first()
        )
    if week is None:
        raise BookingNotFoundError("Booking not found")

    from timetable.core.models import Semester

    semester = db.get(Semester, week.semester_id)
    if semester is None or semester.timetable_session_id != timetable_session_id:
        raise BookingNotFoundError("Booking not found")

    _apply_snapshots(db, {booking_id: target_state})
    after = snapshot_bookings(db, [booking_id])
    return _mutation_result(
        db,
        timetable_session_id=timetable_session_id,
        course_id=course_id,
        header=f"Rollback booking #{booking_id} from resolved change",
        before=current_before,
        after=after,
    )


def export_resolved_change_log_xlsx(
    db: Session,
    *,
    timetable_session_id: int,
) -> Path:
    rows = gather_timetabling_change_log_display_rows(
        db,
        timetable_session_id=timetable_session_id,
        resolved=True,
    )
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    path = Path(tmp.name)
    write_change_log_xlsx(path, rows)
    return path

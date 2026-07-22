"""Change log list, notes, manual records, rollback, and export."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from timetable.constants import DAYS
from timetable.core.booking_snapshots import _slot_to_str, snapshot_bookings
from timetable.core.change_log_data import (
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
            "removed": r.removed,
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
    fields: list[str],
) -> None:
    """Hand-written change record for the chosen fields of a placecard.

    Logs a change that was actioned outside this session's tracking (e.g. on a
    previous version of the file). Only the selected lecturer/time/day/room
    fields are recorded (with the booking's current values); the row always
    appears on the resolved log even though the tracked state shows no change,
    and the admin export highlights exactly those fields.
    """
    booking = _booking_in_session(db, booking_id, timetable_session_id)
    chosen = [f for f in fields if f in ("lecturer", "time", "day", "room")]
    if not chosen:
        raise ValueError("Select at least one field to log")
    values = {
        "lecturer": booking.staff.name if booking.staff else "",
        "time": f"{_slot_to_str(booking.start_slot)}–{_slot_to_str(booking.end_slot)}",
        "day": DAYS[booking.day] if 0 <= booking.day < len(DAYS) else "",
        "room": booking.room.code if booking.room else "",
    }
    row = {
        "id": (booking.external_id or "").strip(),
        "group": booking.course.code if booking.course else "",
        "class": booking.unit.name if booking.unit else "",
        "lecturer_change": values["lecturer"] if "lecturer" in chosen else "",
        "time_change": values["time"] if "time" in chosen else "",
        "day_change": values["day"] if "day" in chosen else "",
        "room_change": values["room"] if "room" in chosen else "",
        "delete": "",
    }
    label = row["class"] or f"booking #{booking_id}"
    entry = ChangeLogEntry(
        timetable_session_id=timetable_session_id,
        action=MANUAL_LOG_ACTION,
        description=(
            f"Manual change record — {label} ({row['group']}): {', '.join(chosen)}".strip()
        ),
        details=json.dumps(
            {"manual": True, "booking_id": booking_id, "fields": chosen, "row": row}
        ),
    )
    db.add(entry)
    db.commit()


def set_change_log_highlight_removed(
    db: Session,
    *,
    timetable_session_id: int,
    entry_id: int,
    booking_id: int,
    removed: bool,
) -> None:
    """Toggle whether a resolved change contributes to the admin-export markup.

    The change stays in the log (shown with a "removed" status); it just stops
    (or resumes) producing a highlight. Manual records store the flag on their
    own entry; tracked net changes store it session-wide per booking so removal
    survives later edits that change which entry is "latest" for the booking.
    """
    entry = db.get(ChangeLogEntry, entry_id)
    if entry is None or entry.timetable_session_id != timetable_session_id:
        raise LookupError("Change log entry not found")

    if is_manual_change_log_entry(entry):
        payload = json.loads(entry.details or "{}")
        if removed:
            payload["manual_removed"] = True
        else:
            payload.pop("manual_removed", None)
        entry.details = json.dumps(payload)
        db.commit()
        return

    key = str(booking_id)
    if removed:
        payload = json.loads(entry.details or "{}")
        removed_net = payload.get("removed_net")
        if not isinstance(removed_net, dict):
            removed_net = {}
        removed_net[key] = True
        payload["removed_net"] = removed_net
        entry.details = json.dumps(payload)
    else:
        # Clear the flag from every entry in the session (it may have been
        # written against a different "latest" entry earlier).
        for e in (
            db.query(ChangeLogEntry)
            .filter(ChangeLogEntry.timetable_session_id == timetable_session_id)
            .all()
        ):
            try:
                payload = json.loads(e.details or "{}")
            except (ValueError, TypeError):
                continue
            removed_net = payload.get("removed_net") if isinstance(payload, dict) else None
            if isinstance(removed_net, dict) and key in removed_net:
                removed_net.pop(key, None)
                if removed_net:
                    payload["removed_net"] = removed_net
                else:
                    payload.pop("removed_net", None)
                e.details = json.dumps(payload)
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

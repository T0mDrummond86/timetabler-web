"""Lecturer cover API helpers."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.booking_snapshots import snapshot_bookings
from timetable.core.cover_lecturers import cover_candidates_with_status
from timetable.core.models import Booking, Staff
from timetable.io.cover_export_pdf import render_cover_timetable_pdf

from .booking_mutations import _booking_in_session, _mutation_result
from .timetable_grid import get_repeating_week


def week_label_for_print(db: Session, timetable_session_id: int) -> str | None:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return None
    label = (week.label or "").strip()
    return label or f"Week {week.week_number}"


def list_cover_candidates(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
) -> list[dict]:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return []
    booking = db.get(Booking, booking_id)
    if booking is None or booking.week_id != week.id:
        raise ValueError("Booking not found")
    week_bookings = db.query(Booking).filter(Booking.week_id == week.id).all()
    rows = cover_candidates_with_status(
        db,
        booking,
        week_bookings,
        timetable_session_id=timetable_session_id,
    )
    return [{"id": s.id, "label": s.name, "busy": busy} for s, busy in rows]


def assign_cover_staff(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
    course_id: int,
    cover_staff_id: int | None,
) -> dict:
    booking = _booking_in_session(db, booking_id, timetable_session_id)
    if cover_staff_id is not None:
        # Any lecturer in this session may be assigned as cover; the UI marks
        # those already teaching the slot, but does not forbid the choice.
        cover_staff = db.get(Staff, cover_staff_id)
        if cover_staff is None or cover_staff.timetable_session_id != timetable_session_id:
            raise ValueError("Selected lecturer is not in this session")

    if booking.cover_staff_id == cover_staff_id:
        from .booking_mutations import NoChangeError

        raise NoChangeError("No changes")

    before = snapshot_bookings(db, [booking_id])
    booking.cover_staff_id = cover_staff_id
    db.flush()
    after = snapshot_bookings(db, [booking_id])
    return _mutation_result(
        db,
        timetable_session_id=timetable_session_id,
        course_id=course_id,
        header="Assign cover lecturer",
        before=before,
        after=after,
    )


def export_cover_timetable_pdf_bytes(
    db: Session,
    *,
    timetable_session_id: int,
    staff_id: int | None = None,
) -> tuple[bytes, str]:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    from .export_filenames import session_export_filename, timetable_session_name

    session_name = timetable_session_name(db, timetable_session_id)
    label = "cover timetable"
    if staff_id is not None:
        staff = db.get(Staff, staff_id)
        if staff:
            label = f"{staff.name} cover timetable"
    filename = session_export_filename(session_name, ".pdf", label=label)
    content = render_cover_timetable_pdf(
        db,
        week_id=week.id,
        staff_id=staff_id,
        week_label=week.label or week_label_for_print(db, timetable_session_id),
    )
    return content, filename

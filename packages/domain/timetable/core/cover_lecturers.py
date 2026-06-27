"""Find lecturers available to cover a class at its scheduled time."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .alternate_slots import _ConstraintContext, _staff_free_at
from .models import Booking, Staff


def cover_candidates_with_status(
    session: Session,
    booking: Booking,
    week_bookings: list[Booking],
    *,
    timetable_session_id: int,
) -> list[tuple[Staff, bool]]:
    """All session lecturers paired with whether they are teaching this slot.

    Returns ``(staff, busy)`` for every lecturer except the class's own
    lecturer(s). ``busy`` is True when that lecturer already has a class
    overlapping this booking's day/time. No availability or competency
    filtering is applied — busyness is surfaced as a marker, not a filter,
    so the caller can still assign a teaching lecturer if they choose.
    """
    others = [b for b in week_bookings if b.id != booking.id]
    ctx = _ConstraintContext.load(session, others)
    day = booking.day
    start = booking.start_slot
    end = booking.end_slot

    staff_rows = (
        session.query(Staff)
        .filter(Staff.timetable_session_id == timetable_session_id)
        .order_by(Staff.name)
        .all()
    )

    out: list[tuple[Staff, bool]] = []
    exclude = {booking.staff_id, booking.sfs_co_teacher_staff_id}
    for person in staff_rows:
        if person.id in exclude:
            continue
        free = _staff_free_at(booking, day, start, end, person.id, others, ctx)
        out.append((person, not free))
    return out

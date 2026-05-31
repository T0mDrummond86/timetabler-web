"""Double-session classes: two timetable bookings per (course, class)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Booking, Unit


def unit_has_double_session(unit: Unit | None) -> bool:
    return unit is not None and bool(getattr(unit, "double_session", 0))


def session_part_durations(unit: Unit) -> tuple[int, int]:
    """Return (part_1_slots, part_2_slots) for a double-session class."""
    total = unit.length_slots or 4
    if not unit_has_double_session(unit):
        return total, 0
    first = unit.double_session_first_slots
    if first is None or first < 1 or first >= total:
        first = max(1, total // 2)
    second = total - first
    if second < 1:
        first = total - 1
        second = 1
    return first, second


def scheduled_session_parts(
    session: Session,
    week_id: int,
    course_id: int,
    unit_id: int,
    *,
    block_week_index: int | None = None,
    semester_week: int | None = None,
) -> set[int]:
    from .booking_sessions import booking_runs_in_semester_week

    parts: set[int] = set()
    q = session.query(Booking).filter(
        Booking.week_id == week_id,
        Booking.course_id == course_id,
        Booking.unit_id == unit_id,
    )
    if block_week_index is None:
        q = q.filter(Booking.block_week_index.is_(None))
    else:
        q = q.filter(Booking.block_week_index == block_week_index)
    for b in q.all():
        if semester_week is not None and not booking_runs_in_semester_week(b, semester_week):
            continue
        parts.add(getattr(b, "session_part", 1) or 1)
    return parts


def course_unit_fully_scheduled(
    session: Session,
    week_id: int,
    course_id: int,
    unit_id: int,
    unit: Unit | None = None,
    *,
    block_week_index: int | None = None,
    semester_week: int | None = None,
) -> bool:
    """True when every required session part exists on the timetable."""
    if unit is None:
        unit = session.get(Unit, unit_id)
    parts = scheduled_session_parts(
        session,
        week_id,
        course_id,
        unit_id,
        block_week_index=block_week_index,
        semester_week=semester_week,
    )
    if unit_has_double_session(unit):
        return 1 in parts and 2 in parts
    return bool(parts)


def double_session_same_day(unit: Unit) -> bool:
    return bool(getattr(unit, "double_session_same_day", 0))

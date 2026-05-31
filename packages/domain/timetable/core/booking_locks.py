"""Timetable locking: timeslots, lecturers, and whole-entity timetables."""
from __future__ import annotations

from .models import Booking, Course, Staff


def effective_lock_time(
    booking: Booking,
    *,
    staff: Staff | None = None,
    course: Course | None = None,
) -> bool:
    """True when this booking's day/start/end must not change."""
    if getattr(booking, "lock_time", 0):
        return True
    if course is not None and getattr(course, "timetable_locked", 0):
        return True
    if staff is not None and getattr(staff, "timetable_locked", 0):
        return True
    return False


def effective_lock_staff(
    booking: Booking,
    *,
    staff: Staff | None = None,
    course: Course | None = None,
) -> bool:
    """True when this booking's assigned lecturer must not change."""
    if getattr(booking, "lock_staff", 0):
        return True
    if course is not None and getattr(course, "timetable_locked", 0):
        return True
    if staff is not None and getattr(staff, "timetable_locked", 0):
        return True
    return False


def booking_stays_scheduled(
    booking: Booking,
    *,
    staff: Staff | None = None,
    course: Course | None = None,
) -> bool:
    """Bookings that remain on the grid when clearing the week to holding areas."""
    return effective_lock_time(booking, staff=staff, course=course) or effective_lock_staff(
        booking, staff=staff, course=course
    )


def lock_summary(
    booking: Booking,
    *,
    staff: Staff | None = None,
    course: Course | None = None,
) -> str:
    lt = effective_lock_time(booking, staff=staff, course=course)
    ls = effective_lock_staff(booking, staff=staff, course=course)
    if lt and ls:
        return "Locked: timeslot and lecturer"
    if lt:
        return "Locked: timeslot"
    if ls:
        return "Locked: lecturer"
    return ""


def filter_movable_booking_ids(
    bookings: list[Booking],
    candidate_ids: list[int] | None,
    *,
    staff_by_id: dict[int, Staff],
    course_by_id: dict[int, Course],
) -> list[int]:
    """Return candidate booking ids (locks do not remove rows — time is pinned in the model)."""
    if candidate_ids is None:
        return [b.id for b in bookings]
    return list(candidate_ids)


def pin_time_in_solver(
    booking: Booking,
    *,
    staff: Staff | None = None,
    course: Course | None = None,
) -> bool:
    """True when the solver must keep this booking's day/start/end unchanged."""
    return effective_lock_time(booking, staff=staff, course=course)


def related_entities(booking: Booking) -> tuple[Staff | None, Course | None]:
    staff = booking.staff if booking.staff is not None else None
    course = booking.course if booking.course is not None else None
    return staff, course

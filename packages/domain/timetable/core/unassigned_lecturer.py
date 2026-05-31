"""Classes that still need a lecturer assigned."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Booking
from .pending_classes import PendingClass, pending_classes_for_week


def bookings_without_lecturer(
    session: Session,
    week_id: int,
    *,
    term_filter: str = "all",
) -> list[Booking]:
    """Scheduled classes in ``week_id`` with no lecturer (on the timetable grid)."""
    q = session.query(Booking).filter(
        Booking.week_id == week_id,
        Booking.staff_id.is_(None),
    )
    if term_filter == "t1":
        q = q.filter(Booking.in_term_1 == 1)
    elif term_filter == "t2":
        q = q.filter(Booking.in_term_2 == 1)
    return q.order_by(Booking.day, Booking.start_slot, Booking.id).all()


def pending_classes_without_lecturer(session: Session, week_id: int) -> list[PendingClass]:
    """Classes not yet placed on the timetable this week (holding area)."""
    return pending_classes_for_week(session, week_id)

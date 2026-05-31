"""Keep timetable bookings in sync when staff rows are removed."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Booking


def clear_lecturer_from_bookings(session: Session, staff_id: int) -> int:
    """Unassign ``staff_id`` from every scheduled class (all weeks).

    Also clears SFS co-teacher when that staff member was assigned in that role.
    Returns the number of booking rows updated. Call before deleting the staff row.
    """
    n_primary = (
        session.query(Booking)
        .filter(Booking.staff_id == staff_id)
        .update({Booking.staff_id: None}, synchronize_session="fetch")
    )
    n_co = (
        session.query(Booking)
        .filter(Booking.sfs_co_teacher_staff_id == staff_id)
        .update(
            {
                Booking.sfs_co_teacher_staff_id: None,
                Booking.sfs_co_teacher_in_term_1: 0,
                Booking.sfs_co_teacher_in_term_2: 0,
            },
            synchronize_session="fetch",
        )
    )
    return n_primary + n_co

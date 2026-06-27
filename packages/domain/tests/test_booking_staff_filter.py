"""Staff/co-teacher booking visibility rules."""
from __future__ import annotations

from timetable.core.booking_staff import staff_active_in_term
from timetable.core.models import Booking


def _booking(*, staff_id: int, co_id: int, co_t1: int, co_t2: int) -> Booking:
    return Booking(
        staff_id=staff_id,
        sfs_co_teacher_staff_id=co_id,
        sfs_co_teacher_in_term_1=co_t1,
        sfs_co_teacher_in_term_2=co_t2,
        in_term_1=1,
        in_term_2=1,
    )


def test_co_teacher_active_when_term_flags_unset():
    booking = _booking(staff_id=1, co_id=2, co_t1=0, co_t2=0)
    assert staff_active_in_term(booking, 2, "t1")
    assert staff_active_in_term(booking, 2, "t2")


def test_co_teacher_inactive_when_class_not_in_term():
    booking = Booking(
        staff_id=1,
        sfs_co_teacher_staff_id=2,
        sfs_co_teacher_in_term_1=0,
        sfs_co_teacher_in_term_2=0,
        in_term_1=0,
        in_term_2=1,
    )
    assert not staff_active_in_term(booking, 2, "t1")
    assert staff_active_in_term(booking, 2, "t2")

"""Co-teacher term-scoped staff hours averaging."""
from __future__ import annotations

from timetable.core.models import Booking, Staff
from timetable.core.staff_hours import staff_hours_snapshot_for_bookings


def _co_teach_booking(*, co_id: int, co_t1: int, co_t2: int) -> Booking:
    primary = Staff(id=1, name="Primary")
    co = Staff(id=co_id, name="Co-Teacher")
    return Booking(
        id=100,
        staff_id=primary.id,
        staff=primary,
        sfs_co_teacher_staff_id=co.id,
        sfs_co_teacher=co,
        sfs_co_teacher_in_term_1=co_t1,
        sfs_co_teacher_in_term_2=co_t2,
        in_term_1=1,
        in_term_2=1,
        start_slot=0,
        end_slot=6,
    )


def test_co_teacher_one_term_averages_half_class_hours():
    """3h class, co-teach T1 only → 1.5h weekly average for the co-teacher."""
    booking = _co_teach_booking(co_id=895, co_t1=1, co_t2=0)
    snap = staff_hours_snapshot_for_bookings([booking], staff_id=895)
    assert snap.regular_avg == 1.5


def test_co_teacher_one_term_not_counted_without_staff_id():
    """Without staff context, class runs both terms → full 3h (legacy aggregate)."""
    booking = _co_teach_booking(co_id=895, co_t1=1, co_t2=0)
    snap = staff_hours_snapshot_for_bookings([booking])
    assert snap.regular_avg == 3.0


def test_co_teacher_one_term_via_peer_ids():
    """Linked sessions match co-teachers by peer staff ids in other campuses."""
    booking = _co_teach_booking(co_id=920, co_t1=1, co_t2=0)
    snap = staff_hours_snapshot_for_bookings(
        [booking],
        staff_id=895,
        staff_peer_ids=[895, 920],
    )
    assert snap.regular_avg == 1.5

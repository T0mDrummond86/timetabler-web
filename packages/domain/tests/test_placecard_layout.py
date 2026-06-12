"""Placecard term-band layout for interactive grids."""
from __future__ import annotations

from timetable.core.models import Booking
from timetable.core.placecard_layout import PlacecardRect, layout_column_bookings, terms_of


def _booking(**kwargs) -> Booking:
    b = Booking(
        week_id=1,
        course_id=1,
        day=kwargs.pop("day", 0),
        start_slot=kwargs.pop("start_slot", 0),
        end_slot=kwargs.pop("end_slot", 2),
        in_term_1=kwargs.pop("in_term_1", 1),
        in_term_2=kwargs.pop("in_term_2", 1),
    )
    b.id = kwargs.pop("id", 1)
    return b


def test_t1_only_uses_left_half():
    b = _booking(id=1, in_term_1=1, in_term_2=0)
    rect = layout_column_bookings([b])[1]
    assert rect.left_pct == 0.0
    assert rect.width_pct == 50.0


def test_t2_only_uses_right_half():
    b = _booking(id=2, in_term_1=0, in_term_2=1)
    rect = layout_column_bookings([b])[2]
    assert rect.left_pct == 50.0
    assert rect.width_pct == 50.0


def test_t1_and_t2_pair_at_same_slot_split_column():
    t1 = _booking(id=1, start_slot=2, end_slot=4, in_term_1=1, in_term_2=0)
    t2 = _booking(id=2, start_slot=2, end_slot=4, in_term_1=0, in_term_2=1)
    layouts = layout_column_bookings([t1, t2])
    assert layouts[1] == PlacecardRect(0.0, 50.0)
    assert layouts[2] == PlacecardRect(50.0, 50.0)


def test_semester_booking_uses_full_width():
    b = _booking(id=3, in_term_1=1, in_term_2=1)
    rect = layout_column_bookings([b])[3]
    assert rect.left_pct == 0.0
    assert rect.width_pct == 100.0


def test_terms_of_reads_integer_flags():
    b = _booking(in_term_1=0, in_term_2=1)
    assert terms_of(b) == (False, True)


def test_overlapping_t1_t2_different_durations_split_bands():
    t1 = _booking(id=1, day=2, start_slot=20, end_slot=23, in_term_1=1, in_term_2=0)
    t2 = _booking(id=2, day=2, start_slot=20, end_slot=24, in_term_1=0, in_term_2=1)
    layouts = layout_column_bookings([t1, t2])
    assert layouts[1] == PlacecardRect(0.0, 50.0)
    assert layouts[2] == PlacecardRect(50.0, 50.0)

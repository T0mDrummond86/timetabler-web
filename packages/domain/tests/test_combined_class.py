"""Combined class detection and clash exemption."""
from __future__ import annotations

from timetable.core.combined_class import (
    component_codes_from_unit,
    detect_combined_class_groups,
    same_combined_class,
)
from timetable.core.models import Booking, Unit


def _booking(
    booking_id: int,
    *,
    course_id: int,
    unit_id: int,
    staff_id: int = 1,
    room_id: int = 1,
    week_id: int = 1,
    day: int = 1,
    start_slot: int = 30,
    end_slot: int = 34,
    combined_class_group_id: int | None = None,
    unit: Unit | None = None,
    in_term_1: int = 1,
    in_term_2: int = 1,
) -> Booking:
    b = Booking(
        week_id=week_id,
        course_id=course_id,
        unit_id=unit_id,
        staff_id=staff_id,
        room_id=room_id,
        day=day,
        start_slot=start_slot,
        end_slot=end_slot,
        combined_class_group_id=combined_class_group_id,
        in_term_1=in_term_1,
        in_term_2=in_term_2,
    )
    b.id = booking_id
    if unit is not None:
        b.unit = unit
    return b


def test_detect_combined_class_three_cohorts_same_units():
    staff_id, room_id = 10, 20
    units = (101, 102, 103)
    courses = (1, 2, 3)
    bookings: list[Booking] = []
    bid = 1
    for course_id in courses:
        for unit_id in units:
            bookings.append(
                _booking(
                    bid,
                    course_id=course_id,
                    unit_id=unit_id,
                    staff_id=staff_id,
                    room_id=room_id,
                )
            )
            bid += 1

    groups = detect_combined_class_groups(bookings)
    assert len(set(groups.values())) == 1
    assert len(groups) == 9


def test_combined_class_exempts_clashes_when_group_id_set():
    staff_id, room_id = 10, 20
    b1 = _booking(1, course_id=1, unit_id=101, staff_id=staff_id, room_id=room_id, combined_class_group_id=7)
    b2 = _booking(2, course_id=2, unit_id=101, staff_id=staff_id, room_id=room_id, combined_class_group_id=7)
    b3 = _booking(3, course_id=1, unit_id=102, staff_id=staff_id, room_id=room_id, combined_class_group_id=7)
    b4 = _booking(4, course_id=2, unit_id=102, staff_id=staff_id, room_id=room_id, combined_class_group_id=7)

    assert same_combined_class(b1, b2)
    assert same_combined_class(b3, b4)

    # validate_bookings needs a session — pairwise logic is covered via same_combined_class
    # in validation; spot-check the helper used by clash detection.
    assert same_combined_class(b1, b3)


def test_different_unit_sets_are_not_combined():
    staff_id, room_id = 10, 20
    bookings = [
        _booking(1, course_id=1, unit_id=101, staff_id=staff_id, room_id=room_id),
        _booking(2, course_id=1, unit_id=102, staff_id=staff_id, room_id=room_id),
        _booking(3, course_id=2, unit_id=103, staff_id=staff_id, room_id=room_id),
    ]
    assert detect_combined_class_groups(bookings) == {}


def test_subset_unit_sets_are_combined():
    staff_id, room_id = 10, 20
    bookings = [
        _booking(1, course_id=1, unit_id=101, staff_id=staff_id, room_id=room_id),
        _booking(2, course_id=1, unit_id=102, staff_id=staff_id, room_id=room_id),
        _booking(3, course_id=1, unit_id=103, staff_id=staff_id, room_id=room_id),
        _booking(4, course_id=2, unit_id=101, staff_id=staff_id, room_id=room_id),
    ]
    groups = detect_combined_class_groups(bookings)
    assert len(set(groups.values())) == 1
    assert set(groups.keys()) == {1, 2, 3, 4}


def test_partial_overlap_without_subset_is_not_combined():
    staff_id, room_id = 10, 20
    bookings = [
        _booking(1, course_id=1, unit_id=101, staff_id=staff_id, room_id=room_id),
        _booking(2, course_id=1, unit_id=102, staff_id=staff_id, room_id=room_id),
        _booking(3, course_id=2, unit_id=102, staff_id=staff_id, room_id=room_id),
        _booking(4, course_id=2, unit_id=103, staff_id=staff_id, room_id=room_id),
    ]
    assert detect_combined_class_groups(bookings) == {}


def test_transitive_subset_links_three_cohorts():
    staff_id, room_id = 10, 20
    bookings = [
        _booking(1, course_id=1, unit_id=101, staff_id=staff_id, room_id=room_id),
        _booking(2, course_id=1, unit_id=102, staff_id=staff_id, room_id=room_id),
        _booking(3, course_id=2, unit_id=101, staff_id=staff_id, room_id=room_id),
        _booking(4, course_id=3, unit_id=101, staff_id=staff_id, room_id=room_id),
        _booking(5, course_id=3, unit_id=102, staff_id=staff_id, room_id=room_id),
        _booking(6, course_id=3, unit_id=103, staff_id=staff_id, room_id=room_id),
    ]
    groups = detect_combined_class_groups(bookings)
    assert len(set(groups.values())) == 1
    assert len(groups) == 6


def test_component_code_subset_with_different_unit_ids():
    staff_id, room_id = 10, 20
    full = Unit(name="ICTCYS604, ICTCYS606, ICTICT618")
    full.id = 501
    partial = Unit(name="ICTCYS604")
    partial.id = 502
    bookings = [
        _booking(1, course_id=1, unit_id=501, staff_id=staff_id, room_id=room_id, unit=full),
        _booking(2, course_id=2, unit_id=502, staff_id=staff_id, room_id=room_id, unit=partial),
    ]
    groups = detect_combined_class_groups(bookings)
    assert len(groups) == 2
    assert len(set(groups.values())) == 1


def test_component_codes_from_unit_name():
    unit = Unit(name="ICTCYS604, ICTCYS606, ICTICT618")
    assert component_codes_from_unit(unit) == frozenset(
        {"ICTCYS604", "ICTCYS606", "ICTICT618"}
    )


def test_component_codes_prefers_component_codes_field():
    unit = Unit(name="Ethics & Cyber Law", component_codes="ICTCYS606, ICTICT618")
    assert component_codes_from_unit(unit) == frozenset({"ICTCYS606", "ICTICT618"})


def test_daniel_paris_tuesday_slot_one_combined_group():
    """Full ICT triple + Ethics cohorts with two-unit subset merge to one session."""
    full = Unit(name="ICTCYS604, ICTCYS606, ICTICT618")
    full.id = 4014
    ethics = Unit(name="Ethics & Cyber Law", component_codes="ICTCYS606, ICTICT618")
    ethics.id = 4026

    def mk(bid: int, cid: int, unit: Unit) -> Booking:
        b = Booking(
            week_id=1,
            course_id=cid,
            unit_id=unit.id,
            staff_id=1,
            room_id=1,
            day=1,
            start_slot=14,
            end_slot=18,
        )
        b.id = bid
        b.unit = unit
        return b

    slot = [
        mk(1, 100, full),
        mk(2, 101, full),
        mk(3, 102, ethics),
        mk(4, 103, ethics),
    ]
    groups = detect_combined_class_groups(slot)
    assert len(set(groups.values())) == 1
    assert len(groups) == 4


def test_single_cohort_multiple_units_not_combined():
    staff_id, room_id = 10, 20
    bookings = [
        _booking(1, course_id=1, unit_id=101, staff_id=staff_id, room_id=room_id),
        _booking(2, course_id=1, unit_id=102, staff_id=staff_id, room_id=room_id),
    ]
    assert detect_combined_class_groups(bookings) == {}


def test_different_rooms_are_not_combined():
    staff_id = 10
    bookings = [
        _booking(1, course_id=1, unit_id=101, staff_id=staff_id, room_id=20),
        _booking(2, course_id=2, unit_id=101, staff_id=staff_id, room_id=21),
    ]
    assert detect_combined_class_groups(bookings) == {}


def test_combined_class_staff_hours_counted_once():
    from timetable.core.staff_hours import _weekly_regular_hours

    staff_id, room_id = 10, 20
    common = dict(
        staff_id=staff_id,
        room_id=room_id,
        start_slot=30,
        end_slot=34,
        in_term_1=1,
        in_term_2=1,
    )
    b1 = _booking(1, course_id=1, unit_id=101, combined_class_group_id=9, **common)
    b2 = _booking(2, course_id=2, unit_id=101, combined_class_group_id=9, **common)
    assert _weekly_regular_hours([b1, b2], 1) == 2.0
    assert _weekly_regular_hours([b1, b2], 1) < _weekly_regular_hours(
        [
            _booking(3, course_id=1, unit_id=101, **common),
            _booking(4, course_id=2, unit_id=101, **common),
        ],
        1,
    )

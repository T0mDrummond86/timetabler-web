"""Detect combined classes: multiple cohorts sharing one teaching session.

A combined class is when two or more course groups are taught together by the
same lecturer, in the same room, at the same timeslot, and the units scheduled
for one cohort form a subset of (or match) the units for another cohort in that
placement. This is not a clash — it is intentional joint delivery.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from sqlalchemy.orm import Session, joinedload

from .models import Booking, Semester, Unit, Week

_VET_CODE = re.compile(r"[A-Z]{2,}\d{2,}[A-Z0-9]*", re.I)


def combined_class_slot_key(b: Booking) -> tuple:
    """Placement identity for combined-class matching (excludes course and unit)."""
    return (
        b.week_id,
        int(b.day),
        int(b.start_slot),
        int(b.end_slot),
        b.staff_id,
        b.room_id,
        int(getattr(b, "in_term_1", 1) or 0),
        int(getattr(b, "in_term_2", 1) or 0),
        getattr(b, "session_weeks", None) or "",
        getattr(b, "block_week_index", None),
        int(getattr(b, "session_part", 1) or 1),
    )


def combine_group_key(b: Booking) -> tuple[str, int] | None:
    """Effective combine-group key: a user merge takes priority over auto-detect.

    Manual merges (``manual_merge_group_id``) and auto-detected combined classes
    (``combined_class_group_id``) are namespaced so their ids never collide.
    """
    manual = getattr(b, "manual_merge_group_id", None)
    if manual is not None:
        return ("m", int(manual))
    auto = getattr(b, "combined_class_group_id", None)
    if auto is not None:
        return ("c", int(auto))
    return None


def same_combined_class(a: Booking, b: Booking) -> bool:
    """True when both bookings belong to the same combined or merged group."""
    key_a = combine_group_key(a)
    return key_a is not None and key_a == combine_group_key(b)


def combined_class_hours_representative_ids(bookings: Iterable[Booking]) -> frozenset[int]:
    """Booking ids that count toward staff hours — one per combined/merged group."""
    by_group: dict[tuple[str, int], list[Booking]] = defaultdict(list)
    for b in bookings:
        key = combine_group_key(b)
        if key is not None:
            by_group[key].append(b)
    reps: set[int] = set()
    for group in by_group.values():
        reps.add(min(b.id for b in group))
    return frozenset(reps)


def counts_toward_staff_hours(
    booking: Booking,
    representative_ids: frozenset[int],
) -> bool:
    """False for duplicate cohort rows in the same combined/merged group."""
    if combine_group_key(booking) is None:
        return True
    return booking.id in representative_ids


def filter_bookings_for_staff_hours(bookings: Iterable[Booking]) -> list[Booking]:
    """Drop duplicate combined-class cohort rows for hour totals."""
    rows = list(bookings)
    rep_ids = combined_class_hours_representative_ids(rows)
    return [b for b in rows if counts_toward_staff_hours(b, rep_ids)]


def component_codes_from_unit(unit: Unit | None) -> frozenset[str]:
    """Parse study-unit codes from a class row (component_codes field, then VET codes in name)."""
    if unit is None:
        return frozenset()
    codes: set[str] = set()

    def _add_from_text(text: str) -> None:
        for match in _VET_CODE.findall(text):
            codes.add(match.upper())

    component_field = (getattr(unit, "component_codes", None) or "").strip()
    if component_field:
        _add_from_text(component_field)
        return frozenset(codes)

    name = (unit.name or "").strip()
    if name:
        _add_from_text(name)
    return frozenset(codes)


def _unit_sets_are_combined_subset(a: frozenset, b: frozenset) -> bool:
    """True when one cohort's units at a placement is a subset of the other's."""
    return bool(a) and bool(b) and (a <= b or b <= a)


def _combined_course_components(course_unit_sets: dict[int, frozenset]) -> list[set[int]]:
    """Group courses linked by subset (or equal) unit sets at one placement."""
    course_ids = list(course_unit_sets.keys())
    if len(course_ids) < 2:
        return []

    parent = {course_id: course_id for course_id in course_ids}

    def find(course_id: int) -> int:
        root = course_id
        while parent[root] != root:
            parent[root] = parent[parent[root]]
            root = parent[root]
        return root

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for i, left_id in enumerate(course_ids):
        left_units = course_unit_sets[left_id]
        for right_id in course_ids[i + 1 :]:
            if _unit_sets_are_combined_subset(left_units, course_unit_sets[right_id]):
                union(left_id, right_id)

    components: dict[int, set[int]] = defaultdict(set)
    for course_id in course_ids:
        components[find(course_id)].add(course_id)

    return [component for component in components.values() if len(component) >= 2]


def _course_unit_set_at_slot(slot_bookings: list[Booking], course_id: int) -> frozenset:
    """Unit signature for one cohort at a placement — prefer component codes."""
    code_set: set[str] = set()
    unit_ids: set[int] = set()
    for b in slot_bookings:
        if b.course_id != course_id or b.unit_id is None:
            continue
        unit_ids.add(int(b.unit_id))
        code_set.update(component_codes_from_unit(getattr(b, "unit", None)))
    if code_set:
        return frozenset(code_set)
    return frozenset(str(uid) for uid in unit_ids)


def detect_combined_class_groups(bookings: Iterable[Booking]) -> dict[int, int]:
    """Map booking id → combined_class_group_id for bookings in a combined class.

    Qualification rules (all must hold):
    - Same lecturer (staff_id), room, and exact timeslot
    - Same term / session-week / block placement flags
    - Two or more distinct courses (cohorts) in one linked group
    - For every pair of courses in the group, one course's unit/component set at
      that placement is a subset of the other's (identical sets also qualify)
    """
    by_slot: dict[tuple, list[Booking]] = defaultdict(list)
    for b in bookings:
        if b.staff_id is None or b.room_id is None:
            continue
        by_slot[combined_class_slot_key(b)].append(b)

    assignment: dict[int, int] = {}
    next_group_id = 1

    for slot_bookings in by_slot.values():
        course_ids = {b.course_id for b in slot_bookings if b.unit_id is not None}
        if len(course_ids) < 2:
            continue

        course_unit_sets = {
            course_id: _course_unit_set_at_slot(slot_bookings, course_id)
            for course_id in course_ids
        }
        course_unit_sets = {
            course_id: unit_set
            for course_id, unit_set in course_unit_sets.items()
            if unit_set
        }
        if len(course_unit_sets) < 2:
            continue

        for course_ids in _combined_course_components(course_unit_sets):
            group_id = next_group_id
            next_group_id += 1
            for b in slot_bookings:
                if b.course_id in course_ids:
                    assignment[b.id] = group_id

    return assignment


def apply_combined_class_detection(session: Session, timetable_session_id: int) -> tuple[int, int]:
    """Recompute combined-class groups for one timetable session.

    Returns (group_count, bookings_tagged).
    """
    week_ids = [
        wid
        for (wid,) in (
            session.query(Week.id)
            .join(Semester, Week.semester_id == Semester.id)
            .filter(Semester.timetable_session_id == timetable_session_id)
            .all()
        )
    ]
    if not week_ids:
        return 0, 0

    bookings = (
        session.query(Booking)
        .options(joinedload(Booking.unit))
        .filter(Booking.week_id.in_(week_ids))
        .all()
    )
    for b in bookings:
        b.combined_class_group_id = None

    groups = detect_combined_class_groups(bookings)
    by_id = {b.id: b for b in bookings}
    for booking_id, group_id in groups.items():
        by_id[booking_id].combined_class_group_id = group_id

    return len(set(groups.values())), len(groups)

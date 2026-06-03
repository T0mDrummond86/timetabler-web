"""Conflict detection and constraint checks.

Returns Violation objects rather than raising — callers decide whether to block
saves (HARD) or warn (SOFT).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from sqlalchemy.orm import Session

from ..constants import DAYS
from .models import (
    Booking,
    Qualification,
    QualificationTimeWindow,
    Staff,
    StaffAvailability,
    StaffCompetency,
    UnitAllowedRoom,
    UnitQualification,
)
from .scheduling_constraints import iter_scheduling_violations
from .booking_staff import (
    staff_booking_hours_by_term,
    staff_ids_with_term_overlap,
    staff_name_on_booking,
    timetable_staff_ids,
)
from .staff_hours import room_is_online


class Severity(str, Enum):
    HARD = "hard"
    SOFT = "soft"


@dataclass(frozen=True)
class Violation:
    severity: Severity
    code: str
    message: str
    booking_ids: tuple[int, ...] = ()


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _hours(start: int, end: int) -> float:
    return (end - start) * 0.5


def validate_bookings(session: Session, week_id: int) -> list[Violation]:
    """Validate all bookings in a given week. Returns ordered list of violations."""
    bookings: list[Booking] = (
        session.query(Booking).filter(Booking.week_id == week_id).all()
    )
    return list(_iter_violations(session, bookings))


def _iter_violations(session: Session, bookings: list[Booking]) -> Iterable[Violation]:
    yield from _check_pairwise_clashes(session, bookings)
    yield from _check_lecturer_constraint(session, bookings)
    yield from _check_room_constraint(session, bookings)
    yield from _check_qualification_windows(session, bookings)
    yield from _check_availability(session, bookings)
    yield from _check_room_capacity(bookings)
    yield from _check_room_type(bookings)
    yield from _check_staff_hour_caps(bookings)
    yield from _check_scheduling_constraints(bookings)


def _terms_overlap(a: Booking, b: Booking) -> bool:
    """Two bookings only really clash if they share at least one term."""
    a_t1 = bool(getattr(a, "in_term_1", 1))
    a_t2 = bool(getattr(a, "in_term_2", 1))
    b_t1 = bool(getattr(b, "in_term_1", 1))
    b_t2 = bool(getattr(b, "in_term_2", 1))
    return (a_t1 and b_t1) or (a_t2 and b_t2)


def _schedules_overlap(session: Session, a: Booking, b: Booking) -> bool:
    """True when two bookings can occur at the same calendar semester week."""
    from .block_delivery import is_block_booking, same_schedule_lane, semester_weeks_overlap

    if is_block_booking(a) or is_block_booking(b):
        if not same_schedule_lane(a, b):
            return semester_weeks_overlap(a, b, session)
        return True
    return _terms_overlap(a, b)


def _room_counts_for_physical_double_booking(room) -> bool:
    """Online rooms are not physical space for double-booking."""
    from .room_types import room_counts_as_physical_space

    return room_counts_as_physical_space(room)


def permitted_parallel_online_cohort_overlap(
    a: Booking,
    b: Booking,
    *,
    a_room=None,
    b_room=None,
) -> bool:
    """Same lecturer running parallel online cohorts of one class — only allowed case."""
    if not (
        a.staff_id is not None
        and a.staff_id == b.staff_id
        and a.unit_id is not None
        and b.unit_id is not None
        and a.unit_id == b.unit_id
        and a.course_id != b.course_id
    ):
        return False
    ra = a_room if a_room is not None else getattr(a, "room", None)
    rb = b_room if b_room is not None else getattr(b, "room", None)
    return room_is_online(ra) and room_is_online(rb)


def bookings_need_separate_lanes(a: Booking, b: Booking, session: Session | None = None) -> bool:
    """True when two bookings overlap in clock time and share a term (real clash)."""
    if not _overlap(a.start_slot, a.end_slot, b.start_slot, b.end_slot):
        return False
    if session is not None:
        return _schedules_overlap(session, a, b)
    return _terms_overlap(a, b)


def _check_pairwise_clashes(session: Session, bookings: list[Booking]) -> Iterable[Violation]:
    by_day: dict[int, list[Booking]] = defaultdict(list)
    for b in bookings:
        by_day[b.day].append(b)
    for day, day_bookings in by_day.items():
        day_bookings.sort(key=lambda b: b.start_slot)
        for i, a in enumerate(day_bookings):
            for b in day_bookings[i + 1 :]:
                if b.start_slot >= a.end_slot:
                    break
                if not _overlap(a.start_slot, a.end_slot, b.start_slot, b.end_slot):
                    continue
                if not _schedules_overlap(session, a, b):
                    continue
                from .block_delivery import same_schedule_lane

                if a.course_id == b.course_id and not same_schedule_lane(a, b):
                    continue
                if (
                    a.room_id
                    and a.room_id == b.room_id
                    and a.room is not None
                    and _room_counts_for_physical_double_booking(a.room)
                ):
                    yield Violation(
                        Severity.HARD,
                        "room_double_booking",
                        f"Room double-booked: {a.room.code} on {DAYS[day]}",
                        (a.id, b.id),
                    )
                shared_staff = set(timetable_staff_ids(a)) & set(timetable_staff_ids(b))
                if shared_staff and not permitted_parallel_online_cohort_overlap(a, b):
                    names = [staff_name_on_booking(a, sid) for sid in sorted(shared_staff)]
                    label = names[0] if len(names) == 1 else ", ".join(names)
                    yield Violation(
                        Severity.HARD,
                        "staff_double_booking",
                        f"Staff double-booked: {label} on {DAYS[day]}",
                        (a.id, b.id),
                    )
                if a.course_id == b.course_id:
                    yield Violation(
                        Severity.HARD,
                        "course_clash",
                        f"Course {a.course.code} has overlapping classes on {DAYS[day]}",
                        (a.id, b.id),
                    )


def _check_lecturer_constraint(session: Session, bookings: list[Booking]) -> Iterable[Violation]:
    """When a class has a non-empty allowed-lecturers list, the booking's
    staff must be in it. Empty list = no constraint."""
    by_unit: dict[int, set[int]] = defaultdict(set)
    for staff_id, unit_id in session.query(StaffCompetency.staff_id, StaffCompetency.unit_id).all():
        by_unit[unit_id].add(staff_id)
    for b in bookings:
        if not (b.staff_id and b.unit_id):
            continue
        allowed = by_unit.get(b.unit_id)
        if allowed and b.staff_id not in allowed:
            yield Violation(
                Severity.SOFT,
                "lecturer_not_allowed",
                f"{b.staff.name} not on allowed-lecturers list for {b.unit.name}",
                (b.id,),
            )


def _check_qualification_windows(session: Session, bookings: list[Booking]) -> Iterable[Violation]:
    """Time-window check is scoped to the booking's *course* → qualification
    link, not every qualification the class happens to be associated with.

    A class can belong to multiple qualifications (e.g. shared between
    Cyber and Networking), but each booking is always for one specific
    course (cohort) which itself belongs to a single qualification. The
    booking's allowed times come from that qualification only.
    """
    windows: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for w in session.query(QualificationTimeWindow).all():
        windows[w.qualification_id].append((w.day, w.start_slot, w.end_slot))
    if not windows:
        return
    qual_names = {q.id: q.name for q in session.query(Qualification).all()}
    for b in bookings:
        if not (b.course and b.course.qualification_id):
            continue
        qid = b.course.qualification_id
        qwindows = windows.get(qid)
        if not qwindows:
            continue
        ok = any(
            d == b.day and s <= b.start_slot and e >= b.end_slot
            for (d, s, e) in qwindows
        )
        if not ok:
            yield Violation(
                Severity.HARD,
                "qualification_time_window",
                f"{b.unit.name if b.unit else '?'} scheduled outside "
                f"{qual_names.get(qid, '?')}'s allowed times",
                (b.id,),
            )


def _check_room_constraint(session: Session, bookings: list[Booking]) -> Iterable[Violation]:
    """When a class has a non-empty allowed-rooms list, the booking's room
    must be in it. Empty list = no constraint."""
    by_unit: dict[int, set[int]] = defaultdict(set)
    for unit_id, room_id in session.query(UnitAllowedRoom.unit_id, UnitAllowedRoom.room_id).all():
        by_unit[unit_id].add(room_id)
    for b in bookings:
        if not (b.room_id and b.unit_id):
            continue
        allowed = by_unit.get(b.unit_id)
        if allowed and b.room_id not in allowed:
            yield Violation(
                Severity.HARD,
                "room_not_allowed",
                f"{b.room.code} not in allowed-rooms list for {b.unit.name}",
                (b.id,),
            )


def _check_availability(session: Session, bookings: list[Booking]) -> Iterable[Violation]:
    avail: dict[int, list[StaffAvailability]] = defaultdict(list)
    for a in session.query(StaffAvailability).all():
        avail[a.staff_id].append(a)
    for b in bookings:
        for sid in timetable_staff_ids(b):
            windows = avail.get(sid)
            if not windows:
                continue  # no windows recorded = treat as always available
            if not any(
                w.day == b.day and w.start_slot <= b.start_slot and w.end_slot >= b.end_slot
                for w in windows
            ):
                name = staff_name_on_booking(b, sid)
                yield Violation(
                    Severity.HARD,
                    "staff_unavailable",
                    f"{name} not available on day {b.day} {b.start_slot}-{b.end_slot}",
                    (b.id,),
                )


def _check_room_capacity(bookings: list[Booking]) -> Iterable[Violation]:
    for b in bookings:
        if b.unit and b.room and b.unit.required_capacity and b.room.capacity:
            if b.room.capacity < b.unit.required_capacity:
                yield Violation(
                    Severity.HARD,
                    "room_capacity",
                    f"{b.room.code} too small for {b.unit.name}",
                    (b.id,),
                )


def _check_room_type(bookings: list[Booking]) -> Iterable[Violation]:
    for b in bookings:
        if b.unit and b.room and b.unit.required_room_type:
            from .room_types import room_types_match

            if not room_types_match(b.unit.required_room_type, b.room.room_type):
                yield Violation(
                    Severity.HARD,
                    "room_type",
                    f"{b.unit.name} requires room type {b.unit.required_room_type}, got {b.room.room_type or '?'}",
                    (b.id,),
                )


def _check_staff_hour_caps(bookings: list[Booking]) -> Iterable[Violation]:
    """Caps apply per term — a lecturer with different classes per term still
    just works the cap each week."""
    t1: dict[int, float] = defaultdict(float)
    t2: dict[int, float] = defaultdict(float)
    for b in bookings:
        for sid in timetable_staff_ids(b):
            t1_h, t2_h = staff_booking_hours_by_term(b, sid)
            t1[sid] += t1_h
            t2[sid] += t2_h
    staff_by_id: dict[int, Staff] = {}
    for b in bookings:
        if b.staff is not None and b.staff_id is not None:
            staff_by_id[b.staff_id] = b.staff
        co = getattr(b, "sfs_co_teacher", None)
        if co is not None and getattr(b, "sfs_co_teacher_staff_id", None) is not None:
            staff_by_id[b.sfs_co_teacher_staff_id] = co
    emitted: set[tuple[int, str]] = set()
    for sid, staff in staff_by_id.items():
        cap = staff.max_hours_per_week
        if cap is None:
            continue
        for term_label, totals in (("T1", t1), ("T2", t2)):
            if totals.get(sid, 0) > cap and (sid, term_label) not in emitted:
                emitted.add((sid, term_label))
                sample_bid = next(
                    (b.id for b in bookings if sid in timetable_staff_ids(b)),
                    None,
                )
                yield Violation(
                    Severity.SOFT,
                    "staff_hour_cap",
                    f"{staff.name} {term_label}: {totals[sid]:.1f}h exceeds cap {cap:.1f}h",
                    (sample_bid,) if sample_bid is not None else (),
                )


def _check_scheduling_constraints(bookings: list[Booking]) -> Iterable[Violation]:
    for severity, code, message, booking_ids in iter_scheduling_violations(bookings):
        yield Violation(
            Severity.HARD if severity == "hard" else Severity.SOFT,
            code,
            message,
            booking_ids,
        )

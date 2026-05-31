"""Build read-only timetable payloads for the web grid."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session, joinedload

from timetable.constants import DAYS, FIRST_SLOT_TIME, NUM_DAYS, NUM_SLOTS, SLOT_MINUTES
from timetable.core.class_colour import booking_class_colour_key
from timetable.core.models import Booking, Course, Semester, Week
from timetable.core.tenancy_models import TimetableSession
from timetable.core.validation import Severity, validate_bookings

from ..colours import class_colours


def _violations_by_booking_id(violations) -> dict[int, list]:
    out: dict[int, list] = defaultdict(list)
    for v in violations:
        for bid in v.booking_ids:
            out[bid].append(v)
    return out


def _assign_lanes(bookings: list[Booking]) -> tuple[dict[int, int], int]:
    from timetable.core.validation import bookings_need_separate_lanes

    sorted_b = sorted(bookings, key=lambda b: (b.start_slot, b.end_slot))
    lane_index: dict[int, int] = {}
    lanes: list[list[Booking]] = []
    for b in sorted_b:
        placed = False
        for i, occupants in enumerate(lanes):
            if any(bookings_need_separate_lanes(b, x) for x in occupants):
                continue
            occupants.append(b)
            lane_index[b.id] = i
            placed = True
            break
        if not placed:
            lanes.append([b])
            lane_index[b.id] = len(lanes) - 1
    return lane_index, max(1, len(lanes))


def _lane_depth_for_booking(booking: Booking, all_day: list[Booking]) -> int:
    depth = 1
    for t in range(booking.start_slot, booking.end_slot):
        active = [b for b in all_day if b.start_slot <= t < b.end_slot]
        _, n_at = _assign_lanes(active)
        depth = max(depth, n_at)
    return depth


def get_repeating_week(db: Session, timetable_session_id: int) -> Week | None:
    sem = (
        db.query(Semester)
        .filter(Semester.timetable_session_id == timetable_session_id)
        .first()
    )
    if sem is None:
        return None
    return (
        db.query(Week)
        .filter(Week.semester_id == sem.id, Week.week_number == 0)
        .first()
    )


def assert_session_in_org(db: Session, session_id: int, org_id: int) -> TimetableSession:
    row = (
        db.query(TimetableSession)
        .filter(
            TimetableSession.id == session_id,
            TimetableSession.organization_id == org_id,
        )
        .first()
    )
    if row is None:
        raise LookupError("Session not found")
    return row


def list_courses(db: Session, timetable_session_id: int) -> list[Course]:
    return (
        db.query(Course)
        .filter(Course.timetable_session_id == timetable_session_id)
        .order_by(Course.code)
        .all()
    )


def build_course_timetable(
    db: Session,
    *,
    timetable_session_id: int,
    course_id: int,
) -> dict:
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.timetable_session_id == timetable_session_id,
        )
        .first()
    )
    if course is None:
        raise LookupError("Course not found")

    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")

    bookings = (
        db.query(Booking)
        .options(
            joinedload(Booking.unit),
            joinedload(Booking.course),
            joinedload(Booking.staff),
            joinedload(Booking.room),
        )
        .filter(
            Booking.week_id == week.id,
            Booking.course_id == course_id,
            Booking.block_week_index.is_(None),
        )
        .all()
    )

    violations = validate_bookings(db, week.id)
    v_by_booking = _violations_by_booking_id(violations)
    hard_ids = {
        bid for v in violations if v.severity == Severity.HARD for bid in v.booking_ids
    }
    soft_ids = {
        bid for v in violations if v.severity == Severity.SOFT for bid in v.booking_ids
    }

    by_day: dict[int, list[Booking]] = defaultdict(list)
    for b in bookings:
        by_day[b.day].append(b)

    cards: list[dict] = []
    for day in range(NUM_DAYS):
        day_bookings = by_day.get(day, [])
        if not day_bookings:
            continue
        lane_index, _n_lanes = _assign_lanes(day_bookings)
        for b in day_bookings:
            lane_depth = _lane_depth_for_booking(b, day_bookings)
            colour_key = booking_class_colour_key(b)
            fill, border = class_colours(colour_key)
            b_violations = v_by_booking.get(b.id, [])
            cards.append(
                {
                    "id": b.id,
                    "day": b.day,
                    "start_slot": b.start_slot,
                    "end_slot": b.end_slot,
                    "lane": lane_index.get(b.id, 0),
                    "lane_depth": lane_depth,
                    "unit_name": b.unit.name if b.unit else None,
                    "course_code": b.course.code if b.course else None,
                    "staff_name": b.staff.name if b.staff else None,
                    "room_code": b.room.code if b.room else None,
                    "notes": b.notes,
                    "external_id": b.external_id,
                    "colour_key": colour_key,
                    "fill_colour": fill,
                    "border_colour": border,
                    "is_hard": b.id in hard_ids,
                    "is_soft": b.id in soft_ids and b.id not in hard_ids,
                    "violations": [
                        {
                            "severity": v.severity.value,
                            "code": v.code,
                            "message": v.message,
                        }
                        for v in b_violations
                    ],
                }
            )

    relevant = [
        v for v in violations if any(bid in {c["id"] for c in cards} for bid in v.booking_ids)
    ]

    return {
        "timetable_session_id": timetable_session_id,
        "course_id": course.id,
        "course_code": course.code,
        "week_id": week.id,
        "week_label": week.label or "Repeating week",
        "days": list(DAYS),
        "num_slots": NUM_SLOTS,
        "slot_minutes": SLOT_MINUTES,
        "first_slot_time": FIRST_SLOT_TIME.strftime("%H:%M"),
        "bookings": cards,
        "violations": [
            {
                "severity": v.severity.value,
                "code": v.code,
                "message": v.message,
                "booking_ids": list(v.booking_ids),
            }
            for v in relevant[:20]
        ],
    }

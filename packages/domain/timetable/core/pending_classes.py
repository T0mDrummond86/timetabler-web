"""Unscheduled classes (holding-area) discovery and seeding for auto-timetable."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..constants import NUM_DAYS, NUM_SLOTS
from .double_session import (
    course_unit_fully_scheduled,
    scheduled_session_parts,
    session_part_durations,
    unit_has_double_session,
)
from .models import Booking, Course, CourseUnit, Unit, UnitQualification


@dataclass(frozen=True)
class PendingClass:
    course_id: int
    unit_id: int
    duration_slots: int
    session_part: int = 1


def unit_ids_for_course(session: Session, course: Course) -> list[int]:
    """Class ids that may be scheduled on this course (qualification + course links)."""
    qual_unit_ids: list[int] = []
    if course.qualification_id is not None:
        qual_unit_ids = [
            uid
            for (uid,) in session.query(UnitQualification.unit_id)
            .filter_by(qualification_id=course.qualification_id)
            .all()
        ]
    course_unit_ids = [
        uid
        for (uid,) in session.query(CourseUnit.unit_id).filter_by(course_id=course.id).all()
    ]
    return sorted({*qual_unit_ids, *course_unit_ids})


def pending_classes_for_week(session: Session, week_id: int) -> list[PendingClass]:
    """Every (course, class[, part]) not yet booked in ``week_id``."""
    pending: list[PendingClass] = []
    for course in session.query(Course).order_by(Course.code).all():
        unit_ids = unit_ids_for_course(session, course)
        if not unit_ids:
            continue
        for uid in unit_ids:
            unit = session.get(Unit, uid)
            if unit is None:
                continue
            if course_unit_fully_scheduled(
                session, week_id, course.id, uid, unit, block_week_index=None
            ):
                continue
            if unit_has_double_session(unit):
                slots1, slots2 = session_part_durations(unit)
                parts = scheduled_session_parts(session, week_id, course.id, uid)
                if 1 not in parts:
                    pending.append(
                        PendingClass(
                            course_id=course.id,
                            unit_id=uid,
                            duration_slots=slots1,
                            session_part=1,
                        )
                    )
                if 2 not in parts:
                    pending.append(
                        PendingClass(
                            course_id=course.id,
                            unit_id=uid,
                            duration_slots=slots2,
                            session_part=2,
                        )
                    )
            else:
                pending.append(
                    PendingClass(
                        course_id=course.id,
                        unit_id=uid,
                        duration_slots=unit.length_slots or 4,
                        session_part=1,
                    )
                )
    return pending


def pending_classes_for_block_week(
    session: Session,
    week_id: int,
    course_id: int,
    block_week_index: int,
) -> list[PendingClass]:
    """Classes available for placement in one block week.

    Unlike the regular repeating week, block delivery often schedules the
    same class on multiple days within the block. Every linked class is
    always returned so the holding area keeps a chip after each drag.
    """
    del week_id, block_week_index  # block bookings are scoped by index, not week row
    course = session.get(Course, course_id)
    if course is None:
        return []
    pending: list[PendingClass] = []
    for uid in unit_ids_for_course(session, course):
        unit = session.get(Unit, uid)
        if unit is None:
            continue
        if unit_has_double_session(unit):
            slots1, _slots2 = session_part_durations(unit)
            pending.append(
                PendingClass(
                    course_id=course_id,
                    unit_id=uid,
                    duration_slots=slots1,
                    session_part=1,
                )
            )
        else:
            pending.append(
                PendingClass(
                    course_id=course_id,
                    unit_id=uid,
                    duration_slots=unit.length_slots or 4,
                    session_part=1,
                )
            )
    return pending


def seed_bookings_for_pending(
    session: Session,
    week_id: int,
    pending: list[PendingClass],
) -> list[Booking]:
    """Create placeholder bookings so the solver can place pending classes.

    Placeholders are staggered across days/slots to avoid an all-overlapping start.
    """
    if not pending:
        return []
    created: list[Booking] = []
    for i, pc in enumerate(pending):
        dur = max(1, min(pc.duration_slots, NUM_SLOTS))
        day = i % NUM_DAYS
        max_start = max(0, NUM_SLOTS - dur)
        start = (i * (dur + 1)) % (max_start + 1) if max_start else 0
        b = Booking(
            week_id=week_id,
            course_id=pc.course_id,
            unit_id=pc.unit_id,
            day=day,
            start_slot=start,
            end_slot=start + dur,
            session_part=pc.session_part,
        )
        from .booking_sessions import initialize_session_weeks

        initialize_session_weeks(b)
        session.add(b)
        created.append(b)
    session.flush()
    return created

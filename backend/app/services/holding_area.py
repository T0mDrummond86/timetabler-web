"""Holding area — unscheduled classes for course, block, and unassigned views."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import Course, Unit
from timetable.core.pending_classes import (
    pending_classes_for_block_week,
    pending_classes_for_course,
    pending_classes_for_week,
)

from .timetable_grid import get_repeating_week


def _serialize_pending(db: Session, pending) -> list[dict]:
    unit_ids = {p.unit_id for p in pending}
    units = {
        u.id: u
        for u in db.query(Unit).filter(Unit.id.in_(unit_ids or [-1])).all()
    }
    return [
        {
            "course_id": p.course_id,
            "unit_id": p.unit_id,
            "unit_name": units[p.unit_id].name if p.unit_id in units else None,
            "duration_slots": p.duration_slots,
            "session_part": p.session_part,
        }
        for p in pending
    ]


def list_holding_area(
    db: Session,
    *,
    timetable_session_id: int,
    kind: str = "course",
    course_id: int | None = None,
    block_week_index: int | None = None,
) -> list[dict]:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return []

    if kind == "unassigned":
        pending = pending_classes_for_week(db, week.id)
        return _serialize_pending(db, pending)

    if kind == "block":
        if course_id is None:
            raise ValueError("course_id is required for block holding area")
        if block_week_index is None:
            raise ValueError("block_week_index is required for block holding area")
        course = (
            db.query(Course)
            .filter(Course.id == course_id, Course.timetable_session_id == timetable_session_id)
            .first()
        )
        if course is None:
            raise LookupError("Course not found")
        pending = pending_classes_for_block_week(
            db, week.id, course_id, block_week_index
        )
        return _serialize_pending(db, pending)

    if course_id is None:
        raise ValueError("course_id is required")
    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.timetable_session_id == timetable_session_id)
        .first()
    )
    if course is None:
        raise LookupError("Course not found")

    pending = pending_classes_for_course(db, week.id, course_id)
    return _serialize_pending(db, pending)

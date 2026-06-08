"""Lightweight counts for dashboard session rows."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from timetable.core.models import Booking, Course, Semester, Week


def session_stats_map(db: Session, session_ids: list[int]) -> dict[int, dict[str, int]]:
    if not session_ids:
        return {}

    course_rows = (
        db.query(Course.timetable_session_id, func.count(Course.id))
        .filter(Course.timetable_session_id.in_(session_ids))
        .group_by(Course.timetable_session_id)
        .all()
    )
    booking_rows = (
        db.query(Semester.timetable_session_id, func.count(Booking.id))
        .join(Week, Week.semester_id == Semester.id)
        .join(Booking, Booking.week_id == Week.id)
        .filter(Semester.timetable_session_id.in_(session_ids))
        .group_by(Semester.timetable_session_id)
        .all()
    )

    out: dict[int, dict[str, int]] = {sid: {"course_count": 0, "booking_count": 0} for sid in session_ids}
    for sid, count in course_rows:
        out[sid]["course_count"] = int(count)
    for sid, count in booking_rows:
        out[sid]["booking_count"] = int(count)
    return out

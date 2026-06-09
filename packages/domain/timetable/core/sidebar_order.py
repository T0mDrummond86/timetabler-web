"""Persisted ordering for course/staff rows in the timetable SELECT sidebar."""
from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .models import Course, Staff


def next_course_sidebar_order(session: Session) -> int:
    current = session.query(func.max(Course.sidebar_order)).scalar()
    return (current if current is not None else -1) + 1


def next_staff_sidebar_order(session: Session) -> int:
    current = session.query(func.max(Staff.sidebar_order)).scalar()
    return (current if current is not None else -1) + 1


def ordered_courses(
    session: Session,
    *,
    include_block_cohorts: bool = False,
    timetable_session_id: int | None = None,
) -> list[Course]:
    q = session.query(Course)
    if timetable_session_id is not None and "timetable_session_id" in Course.__table__.columns:
        q = q.filter(Course.timetable_session_id == timetable_session_id)
    if not include_block_cohorts:
        q = q.filter(
            or_(Course.is_block_cohort == 0, Course.is_block_cohort.is_(None)),
            ~Course.code.like("% Blk Grp%"),
        )
    return (
        q.order_by(Course.sidebar_order, Course.code, Course.id)
        .all()
    )


def ordered_staff(session: Session, *, timetable_session_id: int | None = None) -> list[Staff]:
    q = session.query(Staff)
    if timetable_session_id is not None and "timetable_session_id" in Staff.__table__.columns:
        q = q.filter(Staff.timetable_session_id == timetable_session_id)
    return q.order_by(Staff.sidebar_order, Staff.name, Staff.id).all()


def set_course_sidebar_order(session: Session, course_ids: list[int]) -> None:
    for index, cid in enumerate(course_ids):
        row = session.get(Course, cid)
        if row is not None:
            row.sidebar_order = index


def set_staff_sidebar_order(session: Session, staff_ids: list[int]) -> None:
    for index, sid in enumerate(staff_ids):
        row = session.get(Staff, sid)
        if row is not None:
            row.sidebar_order = index

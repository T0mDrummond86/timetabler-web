"""Add, duplicate, and delete courses (desktop course sidebar menu)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import Booking, Course
from timetable.core.sidebar_order import next_course_sidebar_order


class CourseDuplicateError(ValueError):
    pass


def create_course(
    db: Session,
    *,
    timetable_session_id: int,
    code: str,
    name: str | None = None,
    qualification_id: int | None = None,
) -> Course:
    code = code.strip()
    if not code:
        raise ValueError("Course code is required")
    existing = (
        db.query(Course)
        .filter(Course.timetable_session_id == timetable_session_id, Course.code == code)
        .first()
    )
    if existing is not None:
        raise CourseDuplicateError(f"A course called {code!r} already exists")
    course = Course(
        code=code,
        name=name,
        qualification_id=qualification_id,
        timetable_session_id=timetable_session_id,
        sidebar_order=next_course_sidebar_order(db),
    )
    db.add(course)
    db.flush()
    return course


def duplicate_course(
    db: Session,
    *,
    timetable_session_id: int,
    source_course_id: int,
    new_code: str,
) -> tuple[Course, list[int]]:
    new_code = new_code.strip()
    if not new_code:
        raise ValueError("New course code is required")
    src = (
        db.query(Course)
        .filter(Course.id == source_course_id, Course.timetable_session_id == timetable_session_id)
        .first()
    )
    if src is None:
        raise LookupError("Course not found")
    if (
        db.query(Course)
        .filter(Course.timetable_session_id == timetable_session_id, Course.code == new_code)
        .first()
    ):
        raise CourseDuplicateError(f"A course called {new_code!r} already exists")

    new_course = Course(
        code=new_code,
        name=src.name,
        qualification_id=src.qualification_id,
        timetable_session_id=timetable_session_id,
        sidebar_order=next_course_sidebar_order(db),
        timetable_locked=getattr(src, "timetable_locked", 0),
        block_week_count=getattr(src, "block_week_count", None),
        block_start_semester_week=getattr(src, "block_start_semester_week", None),
    )
    db.add(new_course)
    db.flush()

    cloned_ids: list[int] = []
    for b in db.query(Booking).filter(Booking.course_id == src.id).all():
        nb = Booking(
            week_id=b.week_id,
            course_id=new_course.id,
            unit_id=b.unit_id,
            staff_id=b.staff_id,
            sfs_co_teacher_staff_id=getattr(b, "sfs_co_teacher_staff_id", None),
            sfs_co_teacher_in_term_1=getattr(b, "sfs_co_teacher_in_term_1", 0),
            sfs_co_teacher_in_term_2=getattr(b, "sfs_co_teacher_in_term_2", 0),
            room_id=b.room_id,
            day=b.day,
            start_slot=b.start_slot,
            end_slot=b.end_slot,
            notes=b.notes,
            external_id=b.external_id,
            in_term_1=b.in_term_1,
            in_term_2=b.in_term_2,
            online_student_count=getattr(b, "online_student_count", None),
            lock_time=getattr(b, "lock_time", 0),
            lock_staff=getattr(b, "lock_staff", 0),
            session_part=getattr(b, "session_part", 1),
            session_weeks=getattr(b, "session_weeks", None),
            block_week_index=getattr(b, "block_week_index", None),
        )
        db.add(nb)
        db.flush()
        cloned_ids.append(nb.id)
    return new_course, cloned_ids


def delete_course(db: Session, *, timetable_session_id: int, course_id: int) -> str:
    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.timetable_session_id == timetable_session_id)
        .first()
    )
    if course is None:
        raise LookupError("Course not found")
    code = course.code
    db.query(Booking).filter(Booking.course_id == course_id).delete(synchronize_session=False)
    db.delete(course)
    db.flush()
    return code

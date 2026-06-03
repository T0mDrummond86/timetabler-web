"""Sample timetable data for Phase 2 UI testing."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import (
    Booking,
    Course,
    Qualification,
    Room,
    Semester,
    Staff,
    Unit,
    Week,
)


def seed_demo_timetable(db: Session, timetable_session_id: int) -> dict[str, int]:
    """Create a minimal course view with one booking if the session is empty."""
    existing = (
        db.query(Course).filter(Course.timetable_session_id == timetable_session_id).count()
    )
    if existing:
        return {"skipped": True}

    qual = Qualification(
        timetable_session_id=timetable_session_id,
        name="Demo Qualification",
        num_groups=1,
    )
    course = Course(
        timetable_session_id=timetable_session_id,
        code="Demo GrpA",
        qualification_id=None,
    )
    unit = Unit(
        timetable_session_id=timetable_session_id,
        name="Cyber Foundations",
        length_slots=4,
    )
    unit2 = Unit(
        timetable_session_id=timetable_session_id,
        name="Workshop Lab",
        length_slots=4,
    )
    staff = Staff(
        timetable_session_id=timetable_session_id,
        name="Alex Teacher",
        max_hours_per_week=30.0,
    )
    room = Room(
        timetable_session_id=timetable_session_id,
        code="R101",
        room_type="on-campus",
        capacity=24,
    )
    db.add_all([qual, course, unit, unit2, staff, room])
    db.flush()
    course.qualification_id = qual.id

    sem = (
        db.query(Semester)
        .filter(Semester.timetable_session_id == timetable_session_id)
        .first()
    )
    if sem is None:
        raise RuntimeError("Session has no semester row")
    week = (
        db.query(Week)
        .filter(Week.semester_id == sem.id, Week.week_number == 0)
        .first()
    )
    if week is None:
        raise RuntimeError("Session has no repeating week")

    db.add(
        Booking(
            week_id=week.id,
            course_id=course.id,
            unit_id=unit.id,
            staff_id=staff.id,
            room_id=room.id,
            day=0,
            start_slot=4,
            end_slot=8,
            in_term_1=1,
            in_term_2=1,
        )
    )
    # Second booking different unit Tuesday — tests second day column
    db.add(
        Booking(
            week_id=week.id,
            course_id=course.id,
            unit_id=unit2.id,
            staff_id=staff.id,
            room_id=room.id,
            day=1,
            start_slot=10,
            end_slot=14,
            in_term_1=1,
            in_term_2=1,
        )
    )
    db.flush()
    return {
        "course_id": course.id,
        "booking_count": 2,
    }

"""Seed semester/week rows for a new web timetable session."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import Semester, Week
from timetable.core.tenancy_models import TimetableSession

DEFAULT_SEMESTER_NAME = "Semester 2, 2026"


def seed_timetable_session_data(db: Session, session: TimetableSession) -> None:
    """Create default semester + repeating week (matches desktop ``init_db``)."""
    existing = (
        db.query(Semester)
        .filter(Semester.timetable_session_id == session.id)
        .first()
    )
    if existing is not None:
        return
    sem = Semester(
        timetable_session_id=session.id,
        name=DEFAULT_SEMESTER_NAME,
        num_weeks=18,
        repeating=1,
    )
    db.add(sem)
    db.flush()
    db.add(
        Week(
            semester_id=sem.id,
            week_number=0,
            label="Repeating week",
        )
    )

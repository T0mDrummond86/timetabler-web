"""Academic calendar storage for a global session."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.tenancy_models import CalendarWeek
from timetable.io.calendar_import import parse_calendar_csv


def _week_out(w: CalendarWeek) -> dict:
    return {
        "semester": w.semester,
        "week_number": w.week_number,
        "monday_date": w.monday_date.isoformat() if w.monday_date else None,
        "label": w.label,
    }


def list_calendar_weeks(db: Session, *, global_session_id: int) -> list[dict]:
    rows = (
        db.query(CalendarWeek)
        .filter(CalendarWeek.global_session_id == global_session_id)
        .order_by(CalendarWeek.semester, CalendarWeek.week_number)
        .all()
    )
    return [_week_out(w) for w in rows]


def import_calendar(db: Session, *, global_session_id: int, content: bytes) -> dict:
    parsed = parse_calendar_csv(content)
    teaching = [r for r in parsed if r.week_number > 0]
    if not teaching:
        raise ValueError(
            "No teaching weeks found — is this an NMT academic calendar export?"
        )

    # Replace any existing calendar for this global session.
    db.query(CalendarWeek).filter(
        CalendarWeek.global_session_id == global_session_id
    ).delete()
    for r in teaching:
        db.add(
            CalendarWeek(
                global_session_id=global_session_id,
                semester=r.semester,
                week_number=r.week_number,
                monday_date=r.monday_date,
                label=r.label,
            )
        )
    db.commit()
    return {"imported": len(teaching), "weeks": list_calendar_weeks(db, global_session_id=global_session_id)}

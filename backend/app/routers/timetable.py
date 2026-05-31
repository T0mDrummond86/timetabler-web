"""Read-only timetable grid API (Phase 2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth.deps import AuthContext, get_auth_context, require_editor
from ..database import get_db
from ..schemas import CourseOut, TimetableGridOut
from ..services.demo_seed import seed_demo_timetable
from ..services.timetable_grid import (
    assert_session_in_org,
    build_course_timetable,
    list_courses,
)

router = APIRouter(tags=["timetable"])


@router.get("/sessions/{session_id}/courses", response_model=list[CourseOut])
def session_courses(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return list_courses(db, session_id)


@router.get("/sessions/{session_id}/timetable", response_model=TimetableGridOut)
def session_timetable(
    session_id: int,
    course_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        payload = build_course_timetable(
            db,
            timetable_session_id=session_id,
            course_id=course_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return payload


@router.post("/sessions/{session_id}/seed-demo")
def seed_demo(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Create sample course + bookings for UI testing (no-op if data already exists)."""
    assert_session_in_org(db, session_id, ctx.organization.id)
    result = seed_demo_timetable(db, session_id)
    db.commit()
    return result

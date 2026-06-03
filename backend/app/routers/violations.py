"""Violation dismissal API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth.deps import AuthContext, require_editor
from ..database import get_db
from ..schemas import ViolationDismissRequest
from ..services.timetable_grid import assert_session_in_org
from ..services.violation_dismissals import clear_all_dismissals, dismiss_violation

router = APIRouter(tags=["violations"])


@router.post("/sessions/{session_id}/violation-dismissals")
def create_violation_dismissal(
    session_id: int,
    body: ViolationDismissRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        dismiss_violation(
            db,
            timetable_session_id=session_id,
            booking_id=body.booking_id,
            code=body.code,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"ok": True}


@router.delete("/sessions/{session_id}/violation-dismissals")
def clear_violation_dismissals(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    clear_all_dismissals(db, timetable_session_id=session_id)
    db.commit()
    return {"ok": True}

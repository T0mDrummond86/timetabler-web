"""Timetable session CRUD within an organization."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import GlobalSessionMember, TimetableSession

from ..auth.deps import AuthContext, get_auth_context, require_editor
from ..database import get_db
from ..schemas import TimetableSessionCreate, TimetableSessionOut, TimetableSessionPatch
from ..services.session_seed import seed_timetable_session_data

router = APIRouter(tags=["sessions"])


def _session_out(row: TimetableSession, db: Session) -> TimetableSessionOut:
    member = (
        db.query(GlobalSessionMember)
        .filter(GlobalSessionMember.timetable_session_id == row.id)
        .first()
    )
    gs_id = gs_name = None
    if member is not None:
        from timetable.core.tenancy_models import GlobalSession

        gs = db.get(GlobalSession, member.global_session_id)
        if gs is not None:
            gs_id = gs.id
            gs_name = gs.name
    return TimetableSessionOut(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        global_session_id=gs_id,
        global_session_name=gs_name,
    )


def _session_in_org(db: Session, session_id: int, org_id: int) -> TimetableSession:
    row = (
        db.query(TimetableSession)
        .filter(
            TimetableSession.id == session_id,
            TimetableSession.organization_id == org_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return row


@router.get("/orgs/{org_id}/sessions", response_model=list[TimetableSessionOut])
def list_sessions(
    org_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organization.id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong organization")
    rows = (
        db.query(TimetableSession)
        .filter(TimetableSession.organization_id == org_id)
        .order_by(TimetableSession.name)
        .all()
    )
    return [_session_out(r, db) for r in rows]


@router.post(
    "/orgs/{org_id}/sessions",
    response_model=TimetableSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    org_id: int,
    body: TimetableSessionCreate,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    if ctx.organization.id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong organization")

    name = body.name.strip()
    existing = (
        db.query(TimetableSession)
        .filter(
            TimetableSession.organization_id == org_id,
            TimetableSession.name == name,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session {name!r} already exists",
        )

    row = TimetableSession(
        organization_id=org_id,
        name=name,
        created_by_id=ctx.user.id,
    )
    db.add(row)
    db.flush()
    seed_timetable_session_data(db, row)
    db.commit()
    db.refresh(row)
    return _session_out(row, db)


@router.get("/sessions/{session_id}", response_model=TimetableSessionOut)
def get_session(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    return _session_out(_session_in_org(db, session_id, ctx.organization.id), db)


@router.patch("/sessions/{session_id}", response_model=TimetableSessionOut)
def update_session(
    session_id: int,
    body: TimetableSessionPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    row = _session_in_org(db, session_id, ctx.organization.id)
    name = body.name.strip()
    existing = (
        db.query(TimetableSession)
        .filter(
            TimetableSession.organization_id == ctx.organization.id,
            TimetableSession.name == name,
            TimetableSession.id != session_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session {name!r} already exists",
        )
    row.name = name
    db.commit()
    db.refresh(row)
    return _session_out(row, db)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    row = _session_in_org(db, session_id, ctx.organization.id)
    db.delete(row)
    db.commit()
    return None

"""Timetable session CRUD within an organization."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import GlobalSessionMember, TimetableSession

from ..auth.deps import AuthContext, get_auth_context, require_editor
from ..database import get_db
from ..schemas import (
    TimetableSessionCreate,
    TimetableSessionDuplicate,
    TimetableSessionOut,
    TimetableSessionPatch,
)
from ..services.session_data import duplicate_timetable_session
from ..services.session_seed import seed_timetable_session_data
from ..services.session_stats import session_stats_map
from ..services.global_access import visible_global_session_ids

router = APIRouter(tags=["sessions"])


def _session_out(
    row: TimetableSession,
    db: Session,
    *,
    stats: dict[str, int] | None = None,
) -> TimetableSessionOut:
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
    counts = stats or {}
    return TimetableSessionOut(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        global_session_id=gs_id,
        global_session_name=gs_name,
        course_count=counts.get("course_count", 0),
        booking_count=counts.get("booking_count", 0),
    )


def _session_out_with_stats(row: TimetableSession, db: Session) -> TimetableSessionOut:
    stats = session_stats_map(db, [row.id])
    return _session_out(row, db, stats=stats.get(row.id))


def _visible_sessions_query(db: Session, *, org_id: int, ctx: AuthContext):
    q = db.query(TimetableSession).filter(TimetableSession.organization_id == org_id)
    if ctx.user.is_admin:
        return q
    visible_global_ids = visible_global_session_ids(ctx.user, org_id, db) or []
    if not visible_global_ids:
        return q.filter(TimetableSession.created_by_id == ctx.user.id)
    return (
        q.outerjoin(
            GlobalSessionMember,
            GlobalSessionMember.timetable_session_id == TimetableSession.id,
        )
        .filter(
            or_(
                TimetableSession.created_by_id == ctx.user.id,
                GlobalSessionMember.global_session_id.in_(visible_global_ids),
            )
        )
        .distinct()
    )


def _session_in_org(db: Session, session_id: int, org_id: int, ctx: AuthContext) -> TimetableSession:
    row = (
        _visible_sessions_query(db, org_id=org_id, ctx=ctx)
        .filter(TimetableSession.id == session_id)
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
    rows = _visible_sessions_query(db, org_id=org_id, ctx=ctx).order_by(TimetableSession.name).all()
    stats = session_stats_map(db, [r.id for r in rows])
    return [_session_out(r, db, stats=stats.get(r.id)) for r in rows]


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
    return _session_out_with_stats(_session_in_org(db, session_id, ctx.organization.id, ctx), db)


@router.patch("/sessions/{session_id}", response_model=TimetableSessionOut)
def update_session(
    session_id: int,
    body: TimetableSessionPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    row = _session_in_org(db, session_id, ctx.organization.id, ctx)
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
    return _session_out_with_stats(row, db)


@router.post(
    "/sessions/{session_id}/duplicate",
    response_model=TimetableSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_session(
    session_id: int,
    body: TimetableSessionDuplicate,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    _session_in_org(db, session_id, ctx.organization.id, ctx)
    try:
        row = duplicate_timetable_session(
            db,
            source_session_id=session_id,
            organization_id=ctx.organization.id,
            name=body.name,
            created_by_id=ctx.user.id,
            copy_change_log=body.copy_change_log,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return _session_out_with_stats(row, db)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    row = _session_in_org(db, session_id, ctx.organization.id, ctx)
    db.delete(row)
    db.commit()
    return None

"""Manage per-user edit/read-only access within a global workspace.

Unlike the admin-only grant endpoints in ``admin.py`` (which decide *whether*
someone can see a workspace), these set *what they can do* — group-wide and per
individual session, and manage who belongs to the workspace at all.
Only the workspace's owner (its creator) may change these; platform admins
keep a break-glass path so an orphaned workspace stays recoverable.
"""
from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import (
    ACCESS_EDIT,
    ACCESS_READ_ONLY,
    ACCESS_LEVELS,
    GlobalSessionMember,
    GlobalSessionUserAccess,
    Membership,
    SessionUserAccess,
    TimetableSession,
    User,
)

from ..auth.deps import AuthContext, get_auth_context
from ..database import get_db
from ..schemas import (
    GlobalAccessMatrixOut,
    SessionAccessListOut,
    SessionAccessUserOut,
    SessionAccessLevelPatch,
    UserAccessRowOut,
)
from ..services.global_access import assert_global_user_access
from ..services.session_access import (
    assert_can_manage_access,
    can_manage_access,
    global_session_owner_id,
)

router = APIRouter(tags=["access"])


def _validate_level(level: str) -> str:
    if level not in ACCESS_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"level must be one of {sorted(ACCESS_LEVELS)}",
        )
    return level


def _group_session_ids(db: Session, global_session_id: int) -> list[int]:
    rows = (
        db.query(GlobalSessionMember.timetable_session_id)
        .filter(GlobalSessionMember.global_session_id == global_session_id)
        .all()
    )
    return [r[0] for r in rows]


def _assert_session_in_group(db: Session, session_id: int, global_session_id: int) -> None:
    if session_id not in _group_session_ids(db, global_session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session is not part of this global workspace",
        )


@router.get(
    "/global-sessions/{global_session_id}/access-levels",
    response_model=GlobalAccessMatrixOut,
)
def get_access_matrix(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Every org user's group-wide level plus their per-session overrides."""
    assert_global_user_access(
        db,
        user=ctx.user,
        global_session_id=global_session_id,
        organization_id=ctx.organization.id,
    )
    session_ids = _group_session_ids(db, global_session_id)
    sessions = (
        db.query(TimetableSession)
        .filter(TimetableSession.id.in_(session_ids))
        .order_by(TimetableSession.name)
        .all()
        if session_ids
        else []
    )

    members = (
        db.query(Membership, User)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.organization_id == ctx.organization.id)
        .order_by(User.username)
        .all()
    )
    global_levels = {
        row.user_id: row.level
        for row in db.query(GlobalSessionUserAccess)
        .filter(GlobalSessionUserAccess.global_session_id == global_session_id)
        .all()
    }
    per_session: dict[int, dict[int, str]] = {}
    if session_ids:
        for row in (
            db.query(SessionUserAccess)
            .filter(SessionUserAccess.timetable_session_id.in_(session_ids))
            .all()
        ):
            per_session.setdefault(row.user_id, {})[row.timetable_session_id] = row.level

    return GlobalAccessMatrixOut(
        global_session_id=global_session_id,
        can_manage=can_manage_access(db, ctx.user, global_session_id),
        owner_user_id=global_session_owner_id(db, global_session_id),
        sessions=[
            {
                "id": s.id,
                "name": s.name,
                "created_by_id": s.created_by_id,
            }
            for s in sessions
        ],
        users=[
            UserAccessRowOut(
                user_id=user.id,
                username=user.username,
                name=user.name,
                is_admin=user.is_admin,
                org_role=membership.role,
                global_level=global_levels.get(user.id),
                session_levels=per_session.get(user.id, {}),
            )
            for membership, user in members
        ],
    )


@router.post("/global-sessions/{global_session_id}/users/{user_id}")
def invite_user(
    global_session_id: int,
    user_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Add an existing account in this organisation to the workspace."""
    assert_can_manage_access(db, ctx.user, global_session_id)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    in_org = (
        db.query(Membership)
        .filter(
            Membership.user_id == user_id,
            Membership.organization_id == ctx.organization.id,
        )
        .first()
    )
    if in_org is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That user is not in this organisation",
        )
    existing = (
        db.query(GlobalSessionUserAccess)
        .filter(
            GlobalSessionUserAccess.global_session_id == global_session_id,
            GlobalSessionUserAccess.user_id == user_id,
        )
        .first()
    )
    if existing is None:
        db.add(
            GlobalSessionUserAccess(
                global_session_id=global_session_id,
                user_id=user_id,
                level=ACCESS_EDIT,
                granted_by_id=ctx.user.id,
                granted_at=_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
            )
        )
        db.commit()
    return {"ok": True, "level": ACCESS_EDIT}


@router.delete("/global-sessions/{global_session_id}/users/{user_id}")
def remove_user(
    global_session_id: int,
    user_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Remove someone from the workspace, including any per-session overrides."""
    assert_can_manage_access(db, ctx.user, global_session_id)
    if user_id == global_session_owner_id(db, global_session_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The workspace owner cannot be removed",
        )
    (
        db.query(GlobalSessionUserAccess)
        .filter(
            GlobalSessionUserAccess.global_session_id == global_session_id,
            GlobalSessionUserAccess.user_id == user_id,
        )
        .delete()
    )
    session_ids = _group_session_ids(db, global_session_id)
    if session_ids:
        (
            db.query(SessionUserAccess)
            .filter(
                SessionUserAccess.timetable_session_id.in_(session_ids),
                SessionUserAccess.user_id == user_id,
            )
            .delete(synchronize_session=False)
        )
    db.commit()
    return {"ok": True}


@router.put("/global-sessions/{global_session_id}/access-levels/{user_id}")
def set_group_level(
    global_session_id: int,
    user_id: int,
    body: SessionAccessLevelPatch,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Set a user's default level across every session in the group."""
    assert_can_manage_access(db, ctx.user, global_session_id)
    level = _validate_level(body.level)
    row = (
        db.query(GlobalSessionUserAccess)
        .filter(
            GlobalSessionUserAccess.global_session_id == global_session_id,
            GlobalSessionUserAccess.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That user has no access to this workspace yet",
        )
    row.level = level
    row.granted_by_id = ctx.user.id
    db.commit()
    return {"ok": True, "level": level}


@router.put("/sessions/{session_id}/access-levels/{user_id}")
def set_session_level(
    session_id: int,
    user_id: int,
    body: SessionAccessLevelPatch,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Override a user's level on one session."""
    member = (
        db.query(GlobalSessionMember)
        .filter(GlobalSessionMember.timetable_session_id == session_id)
        .first()
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session is not linked to a global workspace",
        )
    assert_can_manage_access(db, ctx.user, member.global_session_id)
    level = _validate_level(body.level)
    row = (
        db.query(SessionUserAccess)
        .filter(
            SessionUserAccess.timetable_session_id == session_id,
            SessionUserAccess.user_id == user_id,
        )
        .first()
    )
    if row is None:
        row = SessionUserAccess(
            timetable_session_id=session_id,
            user_id=user_id,
            level=level,
            granted_by_id=ctx.user.id,
            created_at=_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
        )
        db.add(row)
    else:
        row.level = level
        row.granted_by_id = ctx.user.id
    db.commit()
    return {"ok": True, "level": level}


@router.delete("/sessions/{session_id}/access-levels/{user_id}")
def clear_session_level(
    session_id: int,
    user_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Drop the per-session override so the group default applies again."""
    member = (
        db.query(GlobalSessionMember)
        .filter(GlobalSessionMember.timetable_session_id == session_id)
        .first()
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session is not linked to a global workspace",
        )
    assert_can_manage_access(db, ctx.user, member.global_session_id)
    (
        db.query(SessionUserAccess)
        .filter(
            SessionUserAccess.timetable_session_id == session_id,
            SessionUserAccess.user_id == user_id,
        )
        .delete()
    )
    db.commit()
    return {"ok": True}


@router.get("/sessions/{session_id}/access-levels", response_model=SessionAccessListOut)
def get_session_access(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Everyone in the org with their effective level on this one session."""
    session_row = db.get(TimetableSession, session_id)
    if session_row is None or session_row.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    member = (
        db.query(GlobalSessionMember)
        .filter(GlobalSessionMember.timetable_session_id == session_id)
        .first()
    )
    global_id = member.global_session_id if member else None

    overrides = {
        row.user_id: row.level
        for row in db.query(SessionUserAccess)
        .filter(SessionUserAccess.timetable_session_id == session_id)
        .all()
    }
    group_levels: dict[int, str] = {}
    if global_id is not None:
        group_levels = {
            row.user_id: row.level
            for row in db.query(GlobalSessionUserAccess)
            .filter(GlobalSessionUserAccess.global_session_id == global_id)
            .all()
        }

    members = (
        db.query(Membership, User)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.organization_id == ctx.organization.id)
        .order_by(User.username)
        .all()
    )

    out: list[SessionAccessUserOut] = []
    for membership, user in members:
        # Mirrors effective_level's order so the page explains itself.
        if user.is_admin:
            source, level = "admin", ACCESS_EDIT
        elif membership.role == "owner":
            source, level = "org owner", ACCESS_EDIT
        elif session_row.created_by_id == user.id:
            source, level = "creator", ACCESS_EDIT
        elif user.id in overrides:
            source, level = "this session", overrides[user.id]
        elif user.id in group_levels:
            source, level = "workspace default", group_levels[user.id]
        else:
            source = "org role"
            level = ACCESS_READ_ONLY if membership.role == "viewer" else ACCESS_EDIT
        out.append(
            SessionAccessUserOut(
                user_id=user.id,
                username=user.username,
                name=user.name,
                is_admin=user.is_admin,
                org_role=membership.role,
                source=source,
                level=level,
                override=overrides.get(user.id),
            )
        )

    return SessionAccessListOut(
        can_manage=(
            can_manage_access(db, ctx.user, global_id) if global_id is not None else False
        ),
        global_session_id=global_id,
        users=out,
    )

"""Per-user edit/read-only permission on timetable sessions.

Sits on top of the visibility rules in ``global_access``/``sessions``: those
decide whether a user can *see* a session, this decides whether they can
*change* it. Read-only users keep full read access, including every export.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import (
    ACCESS_EDIT,
    ACCESS_READ_ONLY,
    GlobalSession,
    GlobalSessionMember,
    GlobalSessionUserAccess,
    Membership,
    SessionUserAccess,
    TimetableSession,
    User,
)

READ_ONLY_DETAIL = "read_only_access"


def _org_role(db: Session, user: User, organization_id: int) -> str | None:
    row = (
        db.query(Membership.role)
        .filter(
            Membership.user_id == user.id,
            Membership.organization_id == organization_id,
        )
        .first()
    )
    return row[0] if row else None


def effective_level(db: Session, user: User, session_id: int) -> str:
    """Resolve a user's permission on one session. First match wins:

    1. platform admin or org owner -> edit
    2. they created the session -> edit
    3. explicit per-session grant -> its level
    4. their group-wide default for the session's global group -> its level
    5. org role "viewer" -> read-only, otherwise edit (today's behaviour)
    """
    if user.is_admin:
        return ACCESS_EDIT

    row = (
        db.query(TimetableSession.created_by_id, TimetableSession.organization_id)
        .filter(TimetableSession.id == session_id)
        .first()
    )
    if row is None:
        return ACCESS_READ_ONLY
    created_by_id, organization_id = row

    role = _org_role(db, user, organization_id)
    if role == "owner":
        return ACCESS_EDIT

    # People always keep control of the sessions they built themselves.
    if created_by_id is not None and created_by_id == user.id:
        return ACCESS_EDIT

    # ...and the owner of a workspace keeps control of everything inside it,
    # so they can never lock themselves out of what they administer.
    owner_row = (
        db.query(GlobalSession.created_by_id)
        .join(
            GlobalSessionMember,
            GlobalSessionMember.global_session_id == GlobalSession.id,
        )
        .filter(GlobalSessionMember.timetable_session_id == session_id)
        .first()
    )
    if owner_row and owner_row[0] is not None and owner_row[0] == user.id:
        return ACCESS_EDIT

    grant = (
        db.query(SessionUserAccess.level)
        .filter(
            SessionUserAccess.timetable_session_id == session_id,
            SessionUserAccess.user_id == user.id,
        )
        .first()
    )
    if grant and grant[0] in (ACCESS_EDIT, ACCESS_READ_ONLY):
        return grant[0]

    group_default = (
        db.query(GlobalSessionUserAccess.level)
        .join(
            GlobalSessionMember,
            GlobalSessionMember.global_session_id
            == GlobalSessionUserAccess.global_session_id,
        )
        .filter(
            GlobalSessionMember.timetable_session_id == session_id,
            GlobalSessionUserAccess.user_id == user.id,
        )
        .first()
    )
    if group_default and group_default[0] in (ACCESS_EDIT, ACCESS_READ_ONLY):
        return group_default[0]

    return ACCESS_READ_ONLY if role == "viewer" else ACCESS_EDIT


def can_edit_session(db: Session, user: User, session_id: int) -> bool:
    return effective_level(db, user, session_id) == ACCESS_EDIT


def assert_can_edit_session(db: Session, user: User, session_id: int) -> None:
    if not can_edit_session(db, user, session_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=READ_ONLY_DETAIL,
        )


def global_session_owner_id(db: Session, global_session_id: int) -> int | None:
    row = (
        db.query(GlobalSession.created_by_id)
        .filter(GlobalSession.id == global_session_id)
        .first()
    )
    return row[0] if row else None


def can_manage_access(db: Session, user: User, global_session_id: int) -> bool:
    """Only the workspace's owner — the person who created it — sets access.

    Platform admins keep a break-glass path so a workspace can still be
    recovered if its owner leaves or is deactivated.
    """
    if user.is_admin:
        return True
    owner_id = global_session_owner_id(db, global_session_id)
    return owner_id is not None and owner_id == user.id


def assert_can_manage_access(db: Session, user: User, global_session_id: int) -> None:
    if not can_manage_access(db, user, global_session_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot manage access for this global workspace",
        )

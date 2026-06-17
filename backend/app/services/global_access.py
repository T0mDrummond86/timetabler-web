"""Per-user access control for global workspaces."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import GlobalSession, GlobalSessionUserAccess, User


def user_can_access_global(user: User, global_session_id: int, db: Session) -> bool:
    if user.is_admin:
        return True
    return (
        db.query(GlobalSessionUserAccess)
        .filter(
            GlobalSessionUserAccess.global_session_id == global_session_id,
            GlobalSessionUserAccess.user_id == user.id,
        )
        .first()
        is not None
    )


def assert_global_user_access(
    db: Session,
    *,
    user: User,
    global_session_id: int,
    organization_id: int,
) -> GlobalSession:
    row = (
        db.query(GlobalSession)
        .filter(
            GlobalSession.id == global_session_id,
            GlobalSession.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Global session not found")
    if not user_can_access_global(user, global_session_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this global workspace",
        )
    return row


def visible_global_session_ids(user: User, org_id: int, db: Session) -> list[int] | None:
    """Return session ids visible to user, or None if admin (all in org)."""
    if user.is_admin:
        return None
    rows = (
        db.query(GlobalSessionUserAccess.global_session_id)
        .join(GlobalSession, GlobalSession.id == GlobalSessionUserAccess.global_session_id)
        .filter(
            GlobalSessionUserAccess.user_id == user.id,
            GlobalSession.organization_id == org_id,
        )
        .all()
    )
    return [r[0] for r in rows]

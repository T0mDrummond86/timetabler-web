"""Admin-only user and global workspace access management."""
from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import (
    GlobalSession,
    GlobalSessionUserAccess,
    Membership,
    User,
)

from ..auth.deps import AuthContext, get_auth_context, require_admin
from ..auth.security import hash_password
from ..database import get_db
from ..schemas import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserPatch,
    GlobalSessionAccessOut,
    GlobalSessionAccessPatch,
)
from ..services.global_access import assert_global_user_access
from ..services.global_sessions import assert_global_in_org
from ..services.users import create_org_user, normalise_username

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_user_out(db: Session, user: User, org_id: int) -> AdminUserOut:
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user.id, Membership.organization_id == org_id)
        .first()
    )
    return AdminUserOut(
        id=user.id,
        username=user.username,
        name=user.name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        role=membership.role if membership else "editor",
    )


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    ctx: AuthContext = Depends(get_auth_context),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    rows = (
        db.query(User)
        .join(Membership, Membership.user_id == User.id)
        .filter(Membership.organization_id == ctx.organization.id)
        .order_by(User.username)
        .all()
    )
    return [_admin_user_out(db, u, ctx.organization.id) for u in rows]


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: AdminUserCreate,
    ctx: AuthContext = Depends(get_auth_context),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    user = create_org_user(
        db,
        organization_id=ctx.organization.id,
        username=body.username,
        password=body.password,
        name=body.name,
        role=body.role,
    )
    db.commit()
    db.refresh(user)
    return _admin_user_out(db, user, ctx.organization.id)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def patch_user(
    user_id: int,
    body: AdminUserPatch,
    ctx: AuthContext = Depends(get_auth_context),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    user = db.get(User, user_id)
    if user is None or user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == user_id,
            Membership.organization_id == ctx.organization.id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if body.name is not None:
        user.name = body.name.strip()
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        user.must_change_password = True
    if body.role is not None:
        membership.role = body.role
    db.commit()
    db.refresh(user)
    return _admin_user_out(db, user, ctx.organization.id)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    user = db.get(User, user_id)
    if user is None or user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == user_id,
            Membership.organization_id == ctx.organization.id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.delete(user)
    db.commit()
    return None


@router.get(
    "/global-sessions/{global_session_id}/access",
    response_model=list[GlobalSessionAccessOut],
)
def list_global_access(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    assert_global_in_org(db, global_session_id, ctx.organization.id)
    rows = (
        db.query(GlobalSessionUserAccess, User)
        .join(User, User.id == GlobalSessionUserAccess.user_id)
        .filter(GlobalSessionUserAccess.global_session_id == global_session_id)
        .order_by(User.username)
        .all()
    )
    return [
        GlobalSessionAccessOut(
            user_id=user.id,
            username=user.username,
            name=user.name,
            granted_at=access.granted_at,
        )
        for access, user in rows
    ]


@router.put(
    "/global-sessions/{global_session_id}/access",
    response_model=list[GlobalSessionAccessOut],
)
def set_global_access(
    global_session_id: int,
    body: GlobalSessionAccessPatch,
    ctx: AuthContext = Depends(get_auth_context),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    assert_global_in_org(db, global_session_id, ctx.organization.id)
    wanted = set(body.user_ids)
    for uid in wanted:
        target = db.get(User, uid)
        if target is None or target.is_admin:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid user id {uid}",
            )
        in_org = (
            db.query(Membership)
            .filter(
                Membership.user_id == uid,
                Membership.organization_id == ctx.organization.id,
            )
            .first()
        )
        if in_org is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"User {uid} is not in this organization",
            )

    existing = (
        db.query(GlobalSessionUserAccess)
        .filter(GlobalSessionUserAccess.global_session_id == global_session_id)
        .all()
    )
    existing_ids = {row.user_id for row in existing}
    for row in existing:
        if row.user_id not in wanted:
            db.delete(row)
    now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    for uid in wanted - existing_ids:
        db.add(
            GlobalSessionUserAccess(
                global_session_id=global_session_id,
                user_id=uid,
                granted_by_id=admin.id,
                granted_at=now,
            )
        )
    db.commit()
    return list_global_access(global_session_id, ctx, admin, db)


@router.get("/global-sessions/{global_session_id}/access/check")
def check_global_access(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Return whether the current user can access this global workspace."""
    row = (
        db.query(GlobalSession)
        .filter(
            GlobalSession.id == global_session_id,
            GlobalSession.organization_id == ctx.organization.id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Global session not found")
    from ..services.global_access import user_can_access_global

    return {"allowed": user_can_access_global(ctx.user, global_session_id, db)}

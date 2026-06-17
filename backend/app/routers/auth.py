"""Authentication routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import (
    Membership,
    Organization,
    TimetableSession,
    User,
)

from ..auth.deps import ensure_password_changed, get_current_user
from ..auth.rate_limit import auth_rate_limiter, client_ip
from ..auth.security import create_access_token, hash_password, verify_password
from ..config import settings
from ..database import get_db
from ..schemas import (
    ChangePasswordRequest,
    LoginRequest,
    OrganizationOut,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from ..services.session_seed import seed_timetable_session_data
from ..services.users import create_org_user, normalise_username
from ..util import unique_org_slug

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_for_user(db: Session, user: User, org_id: int | None) -> TokenResponse:
    if org_id is None:
        m = (
            db.query(Membership)
            .filter(Membership.user_id == user.id)
            .order_by(Membership.id)
            .first()
        )
        if m is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User belongs to no organization",
            )
        org_id = m.organization_id
        role = m.role
    else:
        m = (
            db.query(Membership)
            .filter(
                Membership.user_id == user.id,
                Membership.organization_id == org_id,
            )
            .first()
        )
        if m is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member")
        role = m.role
    token = create_access_token(user_id=user.id, org_id=org_id, role=role)
    return TokenResponse(access_token=token)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled; contact an administrator",
        )
    auth_rate_limiter.check(client_ip(request))

    org = Organization(name=body.organization_name.strip(), slug=unique_org_slug(db, body.organization_name))
    db.add(org)
    db.flush()

    user = create_org_user(
        db,
        organization_id=org.id,
        username=body.username,
        password=body.password,
        name=body.name,
        role="owner",
    )
    user.is_admin = True

    tt_session = TimetableSession(
        organization_id=org.id,
        name="Default",
        created_by_id=user.id,
    )
    db.add(tt_session)
    db.flush()
    seed_timetable_session_data(db, tt_session)
    db.commit()

    return _token_for_user(db, user, org.id)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    auth_rate_limiter.check(client_ip(request))
    username = normalise_username(body.username)
    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    return _token_for_user(db, user, body.organization_id)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", response_model=UserOut)
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be different from the current password",
        )
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.commit()
    db.refresh(user)
    return user


@router.get("/orgs", response_model=list[OrganizationOut])
def my_organizations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_password_changed(user)
    rows = (
        db.query(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .filter(Membership.user_id == user.id)
        .order_by(Organization.name)
        .all()
    )
    return [
        OrganizationOut(id=org.id, name=org.name, slug=org.slug, role=m.role)
        for m, org in rows
    ]

"""Authentication routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import (
    Membership,
    Organization,
    TimetableSession,
    User,
)

from ..auth.deps import get_current_user
from ..auth.security import create_access_token, hash_password, verify_password
from ..database import get_db
from ..schemas import (
    LoginRequest,
    OrganizationOut,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from ..services.session_seed import seed_timetable_session_data
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
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    org = Organization(name=body.organization_name.strip(), slug=unique_org_slug(db, body.organization_name))
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        name=body.name.strip(),
    )
    db.add_all([org, user])
    db.flush()

    db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))

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
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return _token_for_user(db, user, body.organization_id)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/orgs", response_model=list[OrganizationOut])
def my_organizations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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

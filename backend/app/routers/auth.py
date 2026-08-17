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

from ..auth.deps import (
    AuthContext,
    ensure_password_changed,
    get_auth_context,
    get_current_user,
)
from ..auth.rate_limit import auth_rate_limiter, client_ip
from ..auth.security import (
    TOKEN_TYPE_MFA,
    TOKEN_TYPE_MFA_SETUP,
    create_access_token,
    create_pending_token,
    decode_access_token,
    hash_password,
    token_type_of,
    verify_password,
)
from ..config import settings
from ..database import get_db
from ..schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResultOut,
    MfaConfirmOut,
    MfaConfirmRequest,
    MfaSetupOut,
    MfaStatusOut,
    MfaVerifyRequest,
    OrganizationOut,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from ..services import two_factor as tf
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


@router.post("/login", response_model=LoginResultOut)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Check the password, then decide what is still owed.

    A correct password alone is no longer a session: an enrolled account owes a
    code (unless this browser is already trusted), and an unenrolled one owes
    enrolment. Either way the caller gets a pending token that can do nothing
    but finish signing in.
    """
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

    if not settings.require_totp:
        # Break-glass only: the flag exists so a misfiring enrolment block
        # cannot lock every account out at once.
        token = _token_for_user(db, user, body.organization_id)
        return LoginResultOut(access_token=token.access_token)

    if not tf.is_enrolled(user):
        return LoginResultOut(
            mfa_setup_required=True,
            pending_token=create_pending_token(
                user_id=user.id, token_type=TOKEN_TYPE_MFA_SETUP
            ),
        )

    if tf.device_is_trusted(db, user, body.device_token):
        token = _token_for_user(db, user, body.organization_id)
        return LoginResultOut(access_token=token.access_token)

    return LoginResultOut(
        mfa_required=True,
        pending_token=create_pending_token(user_id=user.id, token_type=TOKEN_TYPE_MFA),
    )


def _user_from_pending(
    db: Session, token: str | None, *, expected_type: str
) -> User:
    """The account behind a pending token, or 401.

    Deliberately not a FastAPI dependency: these tokens must never be usable
    through the normal authenticated path, so they are only ever read here.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in again"
        )
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except Exception as exc:  # noqa: BLE001 — any decode failure is the same 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That sign-in attempt expired; start again",
        ) from exc
    if token_type_of(payload) != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in again"
        )
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in again"
        )
    return user


@router.post("/mfa/verify", response_model=LoginResultOut)
def mfa_verify(body: MfaVerifyRequest, request: Request, db: Session = Depends(get_db)):
    """Second step of signing in: a TOTP code, or a recovery code."""
    auth_rate_limiter.check(client_ip(request))
    user = _user_from_pending(db, body.pending_token, expected_type=TOKEN_TYPE_MFA)
    try:
        tf.verify_second_factor(db, user, body.code)
    except tf.TwoFactorError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    token = _token_for_user(db, user, None)
    device_token = (
        tf.remember_device(db, user, body.device_label) if body.remember_device else None
    )
    return LoginResultOut(access_token=token.access_token, pending_token=device_token)


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(
    body: MfaConfirmRequest | None = None,
    db: Session = Depends(get_db),
):
    """Issue a secret to enrol against. Does not enable anything yet.

    Reached with the setup token from a sign-in attempt, since a user who has
    not enrolled cannot hold a session to authenticate with.
    """
    user = _user_from_pending(
        db, (body.pending_token if body else None), expected_type=TOKEN_TYPE_MFA_SETUP
    )
    try:
        secret, uri = tf.begin_enrolment(db, user)
    except tf.TwoFactorError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return MfaSetupOut(
        secret=secret, provisioning_uri=uri, issuer=tf.ISSUER, username=user.username
    )


@router.post("/mfa/confirm", response_model=MfaConfirmOut)
def mfa_confirm(body: MfaConfirmRequest, db: Session = Depends(get_db)):
    """Finish enrolment with a working code; hands back the recovery codes once."""
    user = _user_from_pending(
        db, body.pending_token, expected_type=TOKEN_TYPE_MFA_SETUP
    )
    try:
        codes = tf.confirm_enrolment(db, user, body.code)
    except tf.TwoFactorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    token = _token_for_user(db, user, None)
    return MfaConfirmOut(access_token=token.access_token, recovery_codes=codes)


@router.get("/mfa/status", response_model=MfaStatusOut)
def mfa_status(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """What the signed-in user's second factor looks like."""
    from timetable.core.tenancy_models import UserTrustedDevice

    return MfaStatusOut(
        enrolled=tf.is_enrolled(user),
        required=settings.require_totp,
        unused_recovery_codes=tf.unused_recovery_code_count(db, user),
        trusted_devices=(
            db.query(UserTrustedDevice).filter(UserTrustedDevice.user_id == user.id).count()
        ),
    )


@router.post("/mfa/forget-devices", response_model=MfaStatusOut)
def mfa_forget_devices(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Stop trusting every remembered browser — for a lost or shared machine."""
    tf.forget_devices(db, user)
    return mfa_status(user=user, db=db)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/refresh", response_model=TokenResponse)
def refresh(ctx: AuthContext = Depends(get_auth_context)):
    """Re-issue a token for an already-authenticated caller.

    Gives the phone app a sliding session: it refreshes on each launch, so
    someone who opens it regularly never has to sign in again, while an
    abandoned device still expires on the normal schedule.
    """
    return TokenResponse(
        access_token=create_access_token(
            user_id=ctx.user.id,
            org_id=ctx.organization.id,
            role=ctx.membership.role,
        ),
        token_type="bearer",
    )


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

"""FastAPI dependencies for authenticated requests."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import Membership, Organization, User

from ..database import get_db
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)

EDITOR_ROLES = frozenset({"owner", "editor"})
VIEWER_ROLES = frozenset({"owner", "editor", "viewer"})
PASSWORD_CHANGE_REQUIRED = "password_change_required"


def ensure_password_changed(user: User) -> None:
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PASSWORD_CHANGE_REQUIRED,
        )


@dataclass(frozen=True)
class AuthContext:
    user: User
    organization: Organization
    membership: Membership


def _require_bearer(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if creds is not None and creds.scheme.lower() == "bearer":
        return creds.credentials
    query_token = request.query_params.get("access_token")
    if query_token:
        return query_token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


def get_current_user(
    token: str = Depends(_require_bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def get_auth_context(
    token: str = Depends(_require_bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        org_id = payload.get("org_id")
        if org_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token has no organization; log in again",
            )
        org_id = int(org_id)
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    user = db.get(User, user_id)
    org = db.get(Organization, org_id)
    if user is None or org is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    ensure_password_changed(user)

    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == user.id,
            Membership.organization_id == org.id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this org")

    return AuthContext(user=user, organization=org, membership=membership)


def require_editor(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if ctx.membership.role not in EDITOR_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor access required")
    return ctx


def require_session_editor(
    request: Request,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
) -> AuthContext:
    """Editor rights on the session named in the path.

    Org-level editor rights are necessary but no longer sufficient: a user can
    be set read-only on individual sessions, or across a whole global group.
    Read-only users keep every GET, so exports stay available to them.
    """
    # Imported here: the service imports domain models, which would otherwise
    # make this module part of an import cycle.
    from ..services.session_access import assert_can_edit_session

    raw = request.path_params.get("session_id")
    if raw is None:
        return ctx
    try:
        session_id = int(raw)
    except (TypeError, ValueError):
        return ctx
    assert_can_edit_session(db, ctx.user, session_id)
    return ctx

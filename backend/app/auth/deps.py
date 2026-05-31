"""FastAPI dependencies for authenticated requests."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import Membership, Organization, User

from ..database import get_db
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)

EDITOR_ROLES = frozenset({"owner", "editor"})
VIEWER_ROLES = frozenset({"owner", "editor", "viewer"})


@dataclass(frozen=True)
class AuthContext:
    user: User
    organization: Organization
    membership: Membership


def _require_bearer(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return creds.credentials


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

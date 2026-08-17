"""Password hashing and JWT helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from ..config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7

#: Token kinds. The two-step sign-in issues a token after the password but
#: before the second factor, and that token must not open the app — every
#: authenticated dependency checks this claim, and only ACCESS passes.
TOKEN_TYPE_ACCESS = "access"
#: Password accepted, second factor still owed.
TOKEN_TYPE_MFA = "mfa"
#: Password accepted, account not enrolled yet — good only for enrolling.
TOKEN_TYPE_MFA_SETUP = "mfa_setup"
#: Short, because it is only ever the gap between two form submissions.
PENDING_TOKEN_EXPIRE_MINUTES = 10


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(*, user_id: int, org_id: int | None, role: str | None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org_id": org_id,
        "role": role,
        "typ": TOKEN_TYPE_ACCESS,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_pending_token(*, user_id: int, token_type: str) -> str:
    """A token that proves the password and nothing else.

    Carries no org or role: there is nothing it is allowed to do except finish
    signing in, so it should not look like a session to anything that reads it.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=PENDING_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "typ": token_type,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def token_type_of(payload: dict[str, Any]) -> str:
    """The kind of token this is.

    Tokens minted before two-factor existed carry no ``typ``; they were full
    sessions, so they keep counting as one until they expire. The enrolment
    block is enforced per request against the account, not the token, so an old
    token still cannot skip setup.
    """
    return str(payload.get("typ") or TOKEN_TYPE_ACCESS)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])

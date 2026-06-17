"""User account helpers."""
from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import Membership, User

from ..auth.security import hash_password

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")


def normalise_username(raw: str) -> str:
    return raw.strip().lower()


def validate_username(username: str) -> str:
    if not _USERNAME_RE.match(username):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username must be 3–80 characters: lowercase letters, digits, . _ -",
        )
    return username


def create_org_user(
    db: Session,
    *,
    organization_id: int,
    username: str,
    password: str,
    name: str = "",
    role: str = "editor",
) -> User:
    username = validate_username(normalise_username(username))
    if db.query(User).filter(User.username == username).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    user = User(
        username=username,
        password_hash=hash_password(password),
        name=name.strip(),
        is_admin=False,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=organization_id, role=role))
    return user

"""Shared auth helpers for API tests."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import Membership, Organization, TimetableSession, User

from app.auth.security import hash_password
from app.services.session_seed import seed_timetable_session_data
from app.util import unique_org_slug

os.environ.setdefault("ALLOW_REGISTRATION", "true")


def register_test_user(
    client: TestClient,
    *,
    username: str,
    password: str = "password123",
    name: str = "Test User",
    organization_name: str = "Test Org",
) -> tuple[str, int, int]:
    reg = client.post(
        "/auth/register",
        json={
            "username": username,
            "password": password,
            "name": name,
            "organization_name": organization_name,
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    orgs = client.get("/orgs", headers={"Authorization": f"Bearer {token}"})
    assert orgs.status_code == 200
    org_id = orgs.json()[0]["id"]
    sessions = client.get(f"/orgs/{org_id}/sessions", headers={"Authorization": f"Bearer {token}"})
    assert sessions.status_code == 200
    session_id = sessions.json()[0]["id"]
    return token, org_id, session_id


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def seed_admin_user(db: Session, *, username: str = "admin", password: str = "password123") -> User:
    org = Organization(name="Admin Org", slug=unique_org_slug(db, "Admin Org"))
    user = User(
        username=username,
        password_hash=hash_password(password),
        name="Administrator",
        is_admin=True,
        is_active=True,
        must_change_password=False,
    )
    db.add_all([org, user])
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
    tt = TimetableSession(organization_id=org.id, name="Default", created_by_id=user.id)
    db.add(tt)
    db.flush()
    seed_timetable_session_data(db, tt)
    db.commit()
    db.refresh(user)
    return user

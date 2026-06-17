"""Admin auth and global workspace access control."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parents[1]
DOMAIN = BACKEND.parent / "packages" / "domain"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(DOMAIN))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ALLOW_REGISTRATION"] = "false"

from timetable.core.models import Base  # noqa: E402
from timetable.core.tenancy_models import Membership, TimetableSession  # noqa: E402, F401

from app.auth.security import create_access_token  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from tests.auth_helpers import auth_headers, seed_admin_user  # noqa: E402


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c, SessionLocal
    app.dependency_overrides.clear()


def _login(db, user) -> dict[str, str]:
    m = db.query(Membership).filter(Membership.user_id == user.id).first()
    assert m is not None
    token = create_access_token(user_id=user.id, org_id=m.organization_id, role=m.role)
    return auth_headers(token)


def test_public_register_disabled(client):
    c, _ = client
    res = c.post(
        "/auth/register",
        json={
            "username": "newbie",
            "password": "password123",
            "name": "New",
            "organization_name": "Org",
        },
    )
    assert res.status_code == 403


def test_admin_creates_user_and_grants_global_access(client):
    c, SessionLocal = client
    with SessionLocal() as db:
        admin = seed_admin_user(db, username="admin")
        headers = _login(db, admin)
        m = db.query(Membership).filter(Membership.user_id == admin.id).first()
        org_id = m.organization_id

    create_user = c.post(
        "/admin/users",
        headers=headers,
        json={"username": "editor1", "password": "password123", "name": "Editor One"},
    )
    assert create_user.status_code == 201, create_user.text
    assert create_user.json()["must_change_password"] is True
    editor_id = create_user.json()["id"]

    login = c.post("/auth/login", json={"username": "editor1", "password": "password123"})
    assert login.status_code == 200
    editor_headers = auth_headers(login.json()["access_token"])

    blocked = c.get(f"/orgs/{org_id}/sessions", headers=editor_headers)
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "password_change_required"

    changed = c.post(
        "/auth/change-password",
        headers=editor_headers,
        json={"current_password": "password123", "new_password": "newpassword99"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["must_change_password"] is False

    editor_headers = auth_headers(login.json()["access_token"])
    sessions = c.get(f"/orgs/{org_id}/sessions", headers=editor_headers)
    assert sessions.status_code == 200

    bad_login = c.post("/auth/login", json={"username": "editor1", "password": "password123"})
    assert bad_login.status_code == 401

    good_login = c.post("/auth/login", json={"username": "editor1", "password": "newpassword99"})
    assert good_login.status_code == 200
    editor_headers = auth_headers(good_login.json()["access_token"])

    empty_globals = c.get(f"/orgs/{org_id}/global-sessions", headers=editor_headers)
    assert empty_globals.status_code == 200
    assert empty_globals.json() == []

    create_global = c.post(
        f"/orgs/{org_id}/global-sessions",
        headers=headers,
        json={"name": "Campus group"},
    )
    assert create_global.status_code == 201, create_global.text
    global_id = create_global.json()["id"]

    admin_globals = c.get(f"/orgs/{org_id}/global-sessions", headers=headers)
    assert len(admin_globals.json()) == 1

    still_empty = c.get(f"/orgs/{org_id}/global-sessions", headers=editor_headers)
    assert still_empty.json() == []

    grant = c.put(
        f"/admin/global-sessions/{global_id}/access",
        headers=headers,
        json={"user_ids": [editor_id]},
    )
    assert grant.status_code == 200
    assert len(grant.json()) == 1

    visible = c.get(f"/orgs/{org_id}/global-sessions", headers=editor_headers)
    assert len(visible.json()) == 1
    assert visible.json()[0]["name"] == "Campus group"

    detail = c.get(f"/global-sessions/{global_id}", headers=editor_headers)
    assert detail.status_code == 200

    sessions = c.get(f"/orgs/{org_id}/sessions", headers=editor_headers)
    assert sessions.status_code == 200
    session_ids = [s["id"] for s in sessions.json()]
    link = c.put(
        f"/global-sessions/{global_id}/members",
        headers=editor_headers,
        json={"timetable_session_ids": session_ids[:1]},
    )
    assert link.status_code == 200, link.text
    assert len(link.json()["member_sessions"]) == 1

    editor_create = c.post(
        f"/orgs/{org_id}/global-sessions",
        headers=editor_headers,
        json={"name": "Blocked"},
    )
    assert editor_create.status_code == 403


def test_login_uses_username(client):
    c, SessionLocal = client
    with SessionLocal() as db:
        seed_admin_user(db, username="alice", password="password123")
    res = c.post("/auth/login", json={"username": "alice", "password": "password123"})
    assert res.status_code == 200
    me = c.get("/auth/me", headers=auth_headers(res.json()["access_token"]))
    assert me.json()["username"] == "alice"
    assert me.json()["is_admin"] is True


def test_admin_changes_own_password(client):
    c, SessionLocal = client
    with SessionLocal() as db:
        admin = seed_admin_user(db, username="admin", password="oldadmin99")
        headers = _login(db, admin)

    changed = c.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "oldadmin99", "new_password": "newadmin99"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["must_change_password"] is False

    bad = c.post("/auth/login", json={"username": "admin", "password": "oldadmin99"})
    assert bad.status_code == 401

    good = c.post("/auth/login", json={"username": "admin", "password": "newadmin99"})
    assert good.status_code == 200

    patch_self = c.patch(
        f"/admin/users/{admin.id}",
        headers=headers,
        json={"password": "reset12345"},
    )
    assert patch_self.status_code == 404

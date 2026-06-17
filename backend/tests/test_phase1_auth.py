"""Phase 1 API tests (SQLite in-memory)."""
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
os.environ["ALLOW_REGISTRATION"] = "true"
from timetable.core.tenancy_models import TimetableSession  # noqa: E402, F401

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


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
        yield c
    app.dependency_overrides.clear()


def test_register_login_and_sessions(client: TestClient):
    reg = client.post(
        "/auth/register",
        json={
            "username": "alice",
            "password": "password123",
            "name": "Alice",
            "organization_name": "Joondalup Campus",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    orgs = client.get("/orgs", headers={"Authorization": f"Bearer {token}"})
    assert orgs.status_code == 200
    assert len(orgs.json()) == 1
    org_id = orgs.json()[0]["id"]

    sessions = client.get(
        f"/orgs/{org_id}/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1
    assert sessions.json()[0]["name"] == "Default"

    create = client.post(
        f"/orgs/{org_id}/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Term 2 draft"},
    )
    assert create.status_code == 201
    assert create.json()["name"] == "Term 2 draft"

"""Class custodians API includes linked qualifications."""
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

from timetable.core.models import (  # noqa: E402
    Base,
    Qualification,
    Unit,
    UnitQualification,
)
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
        yield c, SessionLocal
    app.dependency_overrides.clear()


def test_class_custodians_includes_qualifications(client):
    test_client, SessionLocal = client
    r = test_client.post(
        "/auth/register",
        json={
            "email": "cust@test.example",
            "password": "password123",
            "name": "Tester",
            "organization_name": "Test Org",
        },
    )
    assert r.status_code == 201
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org_id = test_client.get("/orgs", headers=headers).json()[0]["id"]
    sid = test_client.post(
        f"/orgs/{org_id}/sessions", headers=headers, json={"name": "S1"}
    ).json()["id"]

    db = SessionLocal()
    unit = Unit(name="Networking 101", timetable_session_id=sid, length_slots=4)
    qual = Qualification(name="Cyber Cert", timetable_session_id=sid, num_groups=1)
    db.add_all([unit, qual])
    db.flush()
    db.add(UnitQualification(unit_id=unit.id, qualification_id=qual.id))
    db.commit()

    resp = test_client.get(f"/sessions/{sid}/class-custodians", headers=headers)
    assert resp.status_code == 200, resp.text
    row = resp.json()["rows"][0]
    assert row["unit_name"] == "Networking 101"
    assert row["qualifications"] == "Cyber Cert"

"""Import staff and qualifications between linked sessions."""
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
    Staff,
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


def _register(client: TestClient) -> tuple[str, int]:
    r = client.post(
        "/auth/register",
        json={
            "email": "import@test.example",
            "password": "password123",
            "name": "Tester",
            "organization_name": "Test Org",
        },
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    org_id = client.get("/orgs", headers={"Authorization": f"Bearer {token}"}).json()[0]["id"]
    return token, org_id


def test_import_staff_and_qualifications_between_linked_sessions(client):
    test_client, SessionLocal = client
    token, org_id = _register(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    id_a = test_client.post(
        f"/orgs/{org_id}/sessions", headers=headers, json={"name": "Source"}
    ).json()["id"]
    id_b = test_client.post(
        f"/orgs/{org_id}/sessions", headers=headers, json={"name": "Target"}
    ).json()["id"]
    gid = test_client.post(
        f"/orgs/{org_id}/global-sessions", headers=headers, json={"name": "Group"}
    ).json()["id"]
    test_client.put(
        f"/global-sessions/{gid}/members",
        headers=headers,
        json={"timetable_session_ids": [id_a, id_b]},
    )

    db = SessionLocal()
    staff = Staff(name="Unique Lecturer", timetable_session_id=id_a, fte=0.8)
    qual = Qualification(
        name="Cyber Qual",
        timetable_session_id=id_a,
        num_groups=3,
        schedule_period="day",
    )
    unit = Unit(name="Intro Cyber", timetable_session_id=id_a, length_slots=4)
    db.add_all([staff, qual, unit])
    db.flush()
    db.add(UnitQualification(unit_id=unit.id, qualification_id=qual.id))
    db.commit()

    opts = test_client.get(
        f"/sessions/{id_b}/import-from-linked/options",
        headers=headers,
        params={"source_session_id": id_a},
    )
    assert opts.status_code == 200
    assert opts.json()["staff"][0]["name"] == "Unique Lecturer"
    assert opts.json()["qualifications"][0]["linked_classes"] == ["Intro Cyber"]

    imp = test_client.post(
        f"/sessions/{id_b}/import-from-linked",
        headers=headers,
        json={
            "source_session_id": id_a,
            "staff_ids": [staff.id],
            "qualification_ids": [qual.id],
        },
    )
    assert imp.status_code == 200, imp.text
    body = imp.json()
    assert body["staff"]["added"] == ["Unique Lecturer"]
    assert body["qualifications"]["added"] == ["Cyber Qual"]
    assert body["qualifications"]["classes_added"] == ["Intro Cyber"]

    db2 = SessionLocal()
    tgt_qual = (
        db2.query(Qualification)
        .filter(Qualification.timetable_session_id == id_b, Qualification.name == "Cyber Qual")
        .one()
    )
    assert tgt_qual.num_groups == 1
    tgt_unit = (
        db2.query(Unit)
        .filter(Unit.timetable_session_id == id_b, Unit.name == "Intro Cyber")
        .one()
    )
    link = (
        db2.query(UnitQualification)
        .filter(
            UnitQualification.unit_id == tgt_unit.id,
            UnitQualification.qualification_id == tgt_qual.id,
        )
        .first()
    )
    assert link is not None

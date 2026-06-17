"""Global session lists amalgamate same-named entities across linked sessions."""
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


def _register(client: TestClient) -> tuple[str, int]:
    r = client.post(
        "/auth/register",
        json={
            "username": "amalg",
            "password": "password123",
            "name": "Tester",
            "organization_name": "Test Org",
        },
    )
    assert r.status_code == 201
    token = r.json()["access_token"]
    org_id = client.get("/orgs", headers={"Authorization": f"Bearer {token}"}).json()[0]["id"]
    return token, org_id


def test_global_units_and_quals_amalgamated_by_name(client):
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
    qual_name = "CIV Cyber stage 1"
    class_name = "Net Admin 101"
    qual_a = Qualification(name=qual_name, timetable_session_id=id_a, num_groups=3)
    qual_b = Qualification(name=qual_name, timetable_session_id=id_b, num_groups=1)
    unit_a = Unit(name=class_name, timetable_session_id=id_a, length_slots=4)
    unit_b = Unit(name=class_name, timetable_session_id=id_b, length_slots=4)
    db.add_all([qual_a, qual_b, unit_a, unit_b])
    db.flush()
    db.add(UnitQualification(unit_id=unit_a.id, qualification_id=qual_a.id))
    db.add(UnitQualification(unit_id=unit_b.id, qualification_id=qual_b.id))
    db.commit()

    units = test_client.get(f"/global-sessions/{gid}/units", headers=headers)
    assert units.status_code == 200
    unit_rows = units.json()["rows"]
    assert len(unit_rows) == 1
    assert unit_rows[0]["name"] == class_name
    assert unit_rows[0]["qualifications"] == qual_name
    assert set(unit_rows[0]["session_names"]) == {"Source", "Target"}

    quals = test_client.get(f"/global-sessions/{gid}/qualifications", headers=headers)
    assert quals.status_code == 200
    qual_rows = quals.json()["rows"]
    assert len(qual_rows) == 1
    assert qual_rows[0]["name"] == qual_name
    assert qual_rows[0]["num_groups"] == 4
    assert set(qual_rows[0]["session_names"]) == {"Source", "Target"}

    cust = test_client.get(f"/global-sessions/{gid}/class-custodians", headers=headers)
    assert cust.status_code == 200
    cust_rows = cust.json()["rows"]
    assert len(cust_rows) == 1
    assert cust_rows[0]["unit_name"] == class_name
    assert set(cust_rows[0]["session_names"]) == {"Source", "Target"}

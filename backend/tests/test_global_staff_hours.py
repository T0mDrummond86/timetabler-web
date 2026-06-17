"""Staff hours propagate across linked global sessions."""
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
    Booking,
    Course,
    Staff,
)
from timetable.core.tenancy_models import TimetableSession  # noqa: E402, F401

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.global_staff_hours import bookings_for_linked_staff, linked_peer_staff
from app.services.session_seed import seed_timetable_session_data
from app.services.timetable_grid import get_repeating_week


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
            "username": "staffhrs",
            "password": "password123",
            "name": "Tester",
            "organization_name": "Test Org",
        },
    )
    assert r.status_code == 201
    token = r.json()["access_token"]
    org_id = client.get("/orgs", headers={"Authorization": f"Bearer {token}"}).json()[0]["id"]
    return token, org_id


def test_import_propagates_hours_profile_and_linked_bookings_count(client):
    test_client, SessionLocal = client
    token, org_id = _register(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    id_a = test_client.post(
        f"/orgs/{org_id}/sessions", headers=headers, json={"name": "Campus A"}
    ).json()["id"]
    id_b = test_client.post(
        f"/orgs/{org_id}/sessions", headers=headers, json={"name": "Campus B"}
    ).json()["id"]
    gid = test_client.post(
        f"/orgs/{org_id}/global-sessions", headers=headers, json={"name": "Group"}
    ).json()["id"]
    test_client.put(
        f"/global-sessions/{gid}/members",
        headers=headers,
        json={"timetable_session_ids": [id_a, id_b]},
    )

    test_client.post(f"/sessions/{id_a}/seed-demo", headers=headers)
    test_client.post(f"/sessions/{id_b}/seed-demo", headers=headers)

    db = SessionLocal()
    staff_a = Staff(
        name="Pat Import",
        timetable_session_id=id_a,
        fte=1.0,
        ot_hours=4.0,
        tae_hours=2.0,
    )
    db.add(staff_a)
    db.commit()
    db.refresh(staff_a)

    imp = test_client.post(
        f"/sessions/{id_b}/import-from-linked",
        headers=headers,
        json={"source_session_id": id_a, "staff_ids": [staff_a.id], "qualification_ids": []},
    )
    assert imp.status_code == 200, imp.text

    db2 = SessionLocal()
    staff_b = (
        db2.query(Staff)
        .filter(Staff.timetable_session_id == id_b, Staff.name == "Pat Import")
        .one()
    )
    assert staff_b.ot_hours == 4.0
    assert staff_b.tae_hours == 2.0

    week_a = get_repeating_week(db2, id_a)
    course_a = db2.query(Course).filter(Course.timetable_session_id == id_a).first()
    assert week_a and course_a
    db2.add(
        Booking(
            week_id=week_a.id,
            course_id=course_a.id,
            staff_id=staff_a.id,
            day=1,
            start_slot=8,
            end_slot=12,
        )
    )
    db2.commit()

    linked_bookings = bookings_for_linked_staff(db2, staff_b)
    assert len(linked_bookings) >= 1

    hours_b = test_client.get(f"/sessions/{id_b}/staff/hours-table", headers=headers)
    assert hours_b.status_code == 200
    row_b = next(r for r in hours_b.json() if r["name"] == "Pat Import")
    assert row_b["total_hours"] is not None
    assert row_b["total_hours"] >= 2.0

    peers = linked_peer_staff(db2, staff_b)
    assert len(peers) == 2


def test_linked_staff_hours_match_across_sessions(client):
    """Timetabled hours in session B must include bookings assigned in session A."""
    test_client, SessionLocal = client
    token, org_id = _register(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    id_a = test_client.post(
        f"/orgs/{org_id}/sessions", headers=headers, json={"name": "Campus A"}
    ).json()["id"]
    id_b = test_client.post(
        f"/orgs/{org_id}/sessions", headers=headers, json={"name": "Campus B"}
    ).json()["id"]
    gid = test_client.post(
        f"/orgs/{org_id}/global-sessions", headers=headers, json={"name": "Group"}
    ).json()["id"]
    test_client.put(
        f"/global-sessions/{gid}/members",
        headers=headers,
        json={"timetable_session_ids": [id_a, id_b]},
    )

    test_client.post(f"/sessions/{id_a}/seed-demo", headers=headers)
    test_client.post(f"/sessions/{id_b}/seed-demo", headers=headers)

    db = SessionLocal()
    staff_a = Staff(name="Alex Cross", timetable_session_id=id_a, fte=1.0)
    db.add(staff_a)
    db.commit()
    db.refresh(staff_a)

    imp = test_client.post(
        f"/sessions/{id_b}/import-from-linked",
        headers=headers,
        json={"source_session_id": id_a, "staff_ids": [staff_a.id], "qualification_ids": []},
    )
    assert imp.status_code == 200, imp.text

    db2 = SessionLocal()
    staff_b = (
        db2.query(Staff)
        .filter(Staff.timetable_session_id == id_b, Staff.name == "Alex Cross")
        .one()
    )
    week_a = get_repeating_week(db2, id_a)
    course_a = db2.query(Course).filter(Course.timetable_session_id == id_a).first()
    assert week_a and course_a
    db2.add(
        Booking(
            week_id=week_a.id,
            course_id=course_a.id,
            staff_id=staff_a.id,
            day=1,
            start_slot=8,
            end_slot=12,
        )
    )
    db2.commit()

    hours_a = test_client.get(f"/sessions/{id_a}/staff/hours-table", headers=headers).json()
    hours_b = test_client.get(f"/sessions/{id_b}/staff/hours-table", headers=headers).json()
    row_a = next(r for r in hours_a if r["name"] == "Alex Cross")
    row_b = next(r for r in hours_b if r["name"] == "Alex Cross")

    assert row_a["in_class_timetabled_hours"] == row_b["in_class_timetabled_hours"]
    assert row_a["total_hours"] == row_b["total_hours"]
    assert row_a["in_class_timetabled_hours"] >= 2.0

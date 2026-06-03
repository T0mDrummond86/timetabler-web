"""Phase 9 — global sessions and cross-session staff busy slots."""
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

from timetable.core.models import Base, Booking, Staff  # noqa: E402
from timetable.core.tenancy_models import TimetableSession  # noqa: E402, F401

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.session_seed import seed_timetable_session_data  # noqa: E402
from app.services.timetable_grid import get_repeating_week  # noqa: E402


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
            "email": "global@test.example",
            "password": "password123",
            "name": "Tester",
            "organization_name": "Test Org",
        },
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    org_id = client.get("/orgs", headers={"Authorization": f"Bearer {token}"}).json()[0]["id"]
    return token, org_id


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_global_session_members_and_linked_busy(client):
    test_client, SessionLocal = client
    token, org_id = _register(test_client)
    headers = _headers(token)

    s1 = test_client.post(
        f"/orgs/{org_id}/sessions", headers=headers, json={"name": "Campus A"}
    )
    s2 = test_client.post(
        f"/orgs/{org_id}/sessions", headers=headers, json={"name": "Campus B"}
    )
    assert s1.status_code == 201 and s2.status_code == 201
    id_a, id_b = s1.json()["id"], s2.json()["id"]

    g = test_client.post(
        f"/orgs/{org_id}/global-sessions",
        headers=headers,
        json={"name": "All campuses"},
    )
    assert g.status_code == 201, g.text
    gid = g.json()["id"]

    put = test_client.put(
        f"/global-sessions/{gid}/members",
        headers=headers,
        json={"timetable_session_ids": [id_a, id_b]},
    )
    assert put.status_code == 200, put.json()["member_sessions"]

    agg = test_client.get(f"/global-sessions/{gid}/staff", headers=headers)
    assert agg.status_code == 200

    demo_a = test_client.post(f"/sessions/{id_a}/seed-demo", headers=headers)
    demo_b = test_client.post(f"/sessions/{id_b}/seed-demo", headers=headers)
    assert demo_a.status_code == 200 and demo_b.status_code == 200

    db = SessionLocal()
    staff_a = (
        db.query(Staff)
        .filter(Staff.timetable_session_id == id_a, Staff.name == "Alex Teacher")
        .first()
    )
    staff_b = (
        db.query(Staff)
        .filter(Staff.timetable_session_id == id_b, Staff.name == "Alex Teacher")
        .first()
    )
    assert staff_a is not None and staff_b is not None
    week_a = get_repeating_week(db, id_a)
    assert week_a is not None
    existing = (
        db.query(Booking)
        .filter(Booking.week_id == week_a.id, Booking.staff_id == staff_a.id, Booking.day == 0)
        .first()
    )
    if existing is None:
        from timetable.core.models import Course

        course = db.query(Course).filter(Course.timetable_session_id == id_a).first()
        assert course is not None
        db.add(
            Booking(
                week_id=week_a.id,
                course_id=course.id,
                unit_id=None,
                staff_id=staff_a.id,
                day=0,
                start_slot=4,
                end_slot=6,
            )
        )
        db.commit()

    grid = test_client.get(
        f"/sessions/{id_b}/timetable",
        headers=headers,
        params={"view": "staff", "staff_id": staff_b.id},
    )
    assert grid.status_code == 200, grid.text
    data = grid.json()
    assert data["linked_session_busy_slots"] is not None
    assert "0" in data["linked_session_busy_slots"]
    assert 4 in data["linked_session_busy_slots"]["0"]

    link = test_client.get(f"/sessions/{id_b}/global-link", headers=headers)
    assert link.json()["linked"] is True
    assert link.json()["global_session_id"] == gid

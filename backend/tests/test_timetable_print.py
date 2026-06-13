"""PDF print timetables."""
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

from timetable.core.models import Base, Booking, Course, Room, Staff, Unit  # noqa: E402
from timetable.core.tenancy_models import TimetableSession  # noqa: E402, F401

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
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


def _register(client: TestClient) -> tuple[str, int, int]:
    r = client.post(
        "/auth/register",
        json={
            "email": "print@test.example",
            "password": "password123",
            "name": "Tester",
            "organization_name": "Print Org",
        },
    )
    assert r.status_code == 201
    token = r.json()["access_token"]
    org_id = client.get("/orgs", headers={"Authorization": f"Bearer {token}"}).json()[0]["id"]
    sid = client.post(
        f"/orgs/{org_id}/sessions", headers={"Authorization": f"Bearer {token}"}, json={"name": "S1"}
    ).json()["id"]
    return token, org_id, sid


def test_print_info_and_pdf(client):
    test_client, SessionLocal = client
    token, _org_id, sid = _register(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    test_client.post(f"/sessions/{sid}/seed-demo", headers=headers)

    info = test_client.get(
        f"/sessions/{sid}/print/timetables/info?kind=course", headers=headers
    )
    assert info.status_code == 200
    data = info.json()
    assert data["week_label"]
    assert len(data["entities"]) >= 1

    db = SessionLocal()
    week = get_repeating_week(db, sid)
    course = db.query(Course).filter(Course.timetable_session_id == sid).first()
    staff = db.query(Staff).filter(Staff.timetable_session_id == sid).first()
    room = db.query(Room).filter(Room.timetable_session_id == sid).first()
    unit = db.query(Unit).filter(Unit.timetable_session_id == sid).first()
    assert week and course and staff and room and unit
    db.add(
        Booking(
            week_id=week.id,
            course_id=course.id,
            unit_id=unit.id,
            staff_id=staff.id,
            room_id=room.id,
            day=0,
            start_slot=8,
            end_slot=12,
        )
    )
    db.commit()

    pdf = test_client.post(
        f"/sessions/{sid}/print/timetables",
        headers=headers,
        json={
            "kind": "course",
            "term_filter": "all",
            "colour_by_class": True,
            "entities": [{"id": course.id, "label": course.code}],
        },
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content[:4] == b"%PDF"
    assert len(pdf.content) > 500

    courses = db.query(Course).filter(Course.timetable_session_id == sid).limit(2).all()
    if len(courses) >= 2:
        multi = test_client.post(
            f"/sessions/{sid}/print/timetables",
            headers=headers,
            json={
                "kind": "course",
                "term_filter": "all",
                "colour_by_class": True,
                "include_index": True,
                "entities": [{"id": c.id, "label": c.code} for c in courses[:2]],
            },
        )
        assert multi.status_code == 200
        assert b"/Outlines" in multi.content or b"/Outline" in multi.content
        assert len(multi.content) > len(pdf.content)

    combo_info = test_client.get(
        f"/sessions/{sid}/print/timetables/info?kind=course_staff", headers=headers
    )
    assert combo_info.status_code == 200
    combo_entities = combo_info.json()["entities"]
    assert combo_entities
    assert any(e.get("entity_kind") == "course" for e in combo_entities)
    assert any(e.get("entity_kind") == "staff" for e in combo_entities)

    combo = test_client.post(
        f"/sessions/{sid}/print/timetables",
        headers=headers,
        json={
            "kind": "course_staff",
            "term_filter": "all",
            "colour_by_class": True,
            "include_index": True,
            "entities": combo_entities[: min(3, len(combo_entities))],
        },
    )
    assert combo.status_code == 200, combo.text
    assert combo.content[:4] == b"%PDF"
    assert len(combo.content) > 500

    empty_changed = test_client.get(
        f"/sessions/{sid}/print/timetables/info?kind=changed_courses", headers=headers
    )
    assert empty_changed.status_code == 200
    assert empty_changed.json()["entities"] == []

    booking = (
        db.query(Booking)
        .filter(Booking.week_id == week.id, Booking.course_id == course.id)
        .first()
    )
    assert booking is not None
    patch = test_client.patch(
        f"/sessions/{sid}/bookings/{booking.id}",
        headers=headers,
        json={"course_id": course.id, "day": 2, "start_slot": 6},
    )
    assert patch.status_code == 200, patch.text

    changed_info = test_client.get(
        f"/sessions/{sid}/print/timetables/info?kind=changed_courses", headers=headers
    )
    assert changed_info.status_code == 200
    changed_entities = changed_info.json()["entities"]
    assert len(changed_entities) == 1
    assert changed_entities[0]["id"] == course.id
    assert changed_entities[0]["label"] == course.code

    changed_pdf = test_client.post(
        f"/sessions/{sid}/print/timetables",
        headers=headers,
        json={
            "kind": "changed_courses",
            "term_filter": "all",
            "colour_by_class": True,
            "entities": changed_entities,
        },
    )
    assert changed_pdf.status_code == 200, changed_pdf.text
    assert changed_pdf.content[:4] == b"%PDF"

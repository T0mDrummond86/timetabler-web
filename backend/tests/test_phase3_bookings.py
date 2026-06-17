"""Phase 3 booking edit, move, undo."""
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

from timetable.core.models import Base, Booking  # noqa: E402

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


def _seed_session(client: TestClient) -> tuple[str, int, int]:
    reg = client.post(
        "/auth/register",
        json={
            "username": "edit",
            "password": "password123",
            "name": "Editor",
            "organization_name": "Edit Org",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org_id = client.get("/orgs", headers=headers).json()[0]["id"]
    session_id = client.get(f"/orgs/{org_id}/sessions", headers=headers).json()[0]["id"]
    client.post(f"/sessions/{session_id}/seed-demo", headers=headers)
    course_id = client.get(f"/sessions/{session_id}/courses", headers=headers).json()[0]["id"]
    grid = client.get(
        f"/sessions/{session_id}/timetable",
        params={"course_id": course_id},
        headers=headers,
    ).json()
    booking_id = grid["bookings"][0]["id"]
    return token, session_id, course_id, booking_id, headers


def test_move_booking(client: TestClient):
    token, session_id, course_id, booking_id, headers = _seed_session(client)

    res = client.patch(
        f"/sessions/{session_id}/bookings/{booking_id}",
        headers=headers,
        json={"course_id": course_id, "day": 2, "start_slot": 6},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    moved = next(b for b in data["grid"]["bookings"] if b["id"] == booking_id)
    assert moved["day"] == 2
    assert moved["start_slot"] == 6
    assert data["change"]["description"] == "Move booking"


def test_patch_notes(client: TestClient):
    _token, session_id, course_id, booking_id, headers = _seed_session(client)

    res = client.patch(
        f"/sessions/{session_id}/bookings/{booking_id}",
        headers=headers,
        json={"course_id": course_id, "notes": "Lab session"},
    )
    assert res.status_code == 200, res.text
    moved = next(b for b in res.json()["grid"]["bookings"] if b["id"] == booking_id)
    assert moved["notes"] == "Lab session"


def test_locked_booking_rejects_move(client: TestClient):
    _token, session_id, course_id, booking_id, headers = _seed_session(client)

    def override_get_db():
        db = next(iter(client.app.dependency_overrides[get_db]()))  # type: ignore
        yield db

    # Set lock directly via test db session from fixture is awkward; use API patch after lock
    # Lock via direct DB in override - simpler: patch booking with lock_time via sqlalchemy
    from app.database import get_db as gdb

    gen = client.app.dependency_overrides[gdb]()
    db = next(gen)
    booking = db.get(Booking, booking_id)
    booking.lock_time = 1
    db.commit()
    try:
        gen.close()
    except StopIteration:
        pass

    res = client.patch(
        f"/sessions/{session_id}/bookings/{booking_id}",
        headers=headers,
        json={"course_id": course_id, "day": 3, "start_slot": 4},
    )
    assert res.status_code == 409
    assert "locked" in res.json()["detail"].lower()


def test_undo_redo_round_trip(client: TestClient):
    _token, session_id, course_id, booking_id, headers = _seed_session(client)

    move = client.patch(
        f"/sessions/{session_id}/bookings/{booking_id}",
        headers=headers,
        json={"course_id": course_id, "day": 3, "start_slot": 5},
    )
    assert move.status_code == 200
    change = move.json()["change"]
    original_day = change["before"][str(booking_id)]["day"]

    undo = client.post(
        f"/sessions/{session_id}/bookings/restore",
        headers=headers,
        json={
            "course_id": course_id,
            "action": "undo",
            "label": change["description"],
            "snapshots": change["before"],
        },
    )
    assert undo.status_code == 200, undo.text
    undone = next(b for b in undo.json()["grid"]["bookings"] if b["id"] == booking_id)
    assert undone["day"] == original_day

    redo = client.post(
        f"/sessions/{session_id}/bookings/restore",
        headers=headers,
        json={
            "course_id": course_id,
            "action": "redo",
            "label": change["description"],
            "snapshots": change["after"],
        },
    )
    assert redo.status_code == 200
    redone = next(b for b in redo.json()["grid"]["bookings"] if b["id"] == booking_id)
    assert redone["day"] == 3


def test_staff_and_rooms_lists(client: TestClient):
    _token, session_id, _course_id, _booking_id, headers = _seed_session(client)

    staff = client.get(f"/sessions/{session_id}/staff", headers=headers)
    rooms = client.get(f"/sessions/{session_id}/rooms", headers=headers)
    assert staff.status_code == 200
    assert rooms.status_code == 200
    assert len(staff.json()) >= 1
    assert len(rooms.json()) >= 1

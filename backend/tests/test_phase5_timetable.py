"""Phase 5 staff/room views and entity editors."""
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

from timetable.core.models import Base  # noqa: E402

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


def _register(client: TestClient) -> tuple[str, int]:
    reg = client.post(
        "/auth/register",
        json={
            "email": "phase5@example.com",
            "password": "password123",
            "name": "Phase Five",
            "organization_name": "Test Org",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    org_id = client.get("/orgs", headers={"Authorization": f"Bearer {token}"}).json()[0]["id"]
    session_id = client.get(
        f"/orgs/{org_id}/sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()[0]["id"]
    return token, session_id


def _seed(client: TestClient, token: str, session_id: int) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    seed = client.post(f"/sessions/{session_id}/seed-demo", headers=headers)
    assert seed.status_code == 200
    return seed.json()


def test_staff_timetable_view(client: TestClient):
    token, session_id = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    _seed(client, token, session_id)

    staff = client.get(f"/sessions/{session_id}/staff", headers=headers).json()
    assert len(staff) == 1
    staff_id = staff[0]["id"]

    grid = client.get(
        f"/sessions/{session_id}/timetable",
        params={"view": "staff", "staff_id": staff_id},
        headers=headers,
    )
    assert grid.status_code == 200, grid.text
    data = grid.json()
    assert data["view"] == "staff"
    assert data["entity_label"] == "Alex Teacher"
    assert data["column_kind"] == "day"
    assert len(data["bookings"]) == 2
    assert all(b["course_code"] == "Demo GrpA" for b in data["bookings"])


def test_room_timetable_view(client: TestClient):
    token, session_id = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    _seed(client, token, session_id)

    grid = client.get(
        f"/sessions/{session_id}/timetable",
        params={"view": "room", "day": 0},
        headers=headers,
    )
    assert grid.status_code == 200, grid.text
    data = grid.json()
    assert data["view"] == "room"
    assert data["column_kind"] == "room"
    assert data["focus_day"] == 0
    assert data["columns"] == ["R101"]
    assert len(data["bookings"]) == 1
    assert data["bookings"][0]["column"] == 0


def test_entity_patch_staff_and_room(client: TestClient):
    token, session_id = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    _seed(client, token, session_id)

    staff = client.get(f"/sessions/{session_id}/staff", headers=headers).json()[0]
    rooms = client.get(f"/sessions/{session_id}/rooms", headers=headers).json()[0]

    patched_staff = client.patch(
        f"/sessions/{session_id}/staff/{staff['id']}",
        json={"name": "Alex Updated", "fte": 0.8},
        headers=headers,
    )
    assert patched_staff.status_code == 200
    assert patched_staff.json()["name"] == "Alex Updated"
    assert patched_staff.json()["fte"] == 0.8

    patched_room = client.patch(
        f"/sessions/{session_id}/rooms/{rooms['id']}",
        json={"code": "R102", "capacity": 30},
        headers=headers,
    )
    assert patched_room.status_code == 200
    assert patched_room.json()["code"] == "R102"
    assert patched_room.json()["capacity"] == 30


def test_health_reports_phase_five(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["phase"] == 8

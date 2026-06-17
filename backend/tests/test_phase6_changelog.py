"""Phase 6 change log UI (no solver)."""
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


def _seed(client: TestClient) -> tuple[str, int, int, int, dict]:
    reg = client.post(
        "/auth/register",
        json={
            "username": "changelog",
            "password": "password123",
            "name": "Log Tester",
            "organization_name": "Log Org",
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


def test_change_log_lists_moves(client: TestClient):
    _token, session_id, course_id, booking_id, headers = _seed(client)

    client.patch(
        f"/sessions/{session_id}/bookings/{booking_id}",
        headers=headers,
        json={"course_id": course_id, "day": 2, "start_slot": 6},
    )

    full = client.get(f"/sessions/{session_id}/change-log", headers=headers)
    assert full.status_code == 200, full.text
    data = full.json()
    assert data["mode"] == "full"
    assert len(data["rows"]) >= 1
    assert data["rows"][0]["action"] == "change"
    assert data["rows"][0]["row"]["day_change"] or data["rows"][0]["row"]["time_change"]


def test_change_log_resolved_and_note(client: TestClient):
    _token, session_id, course_id, booking_id, headers = _seed(client)

    client.patch(
        f"/sessions/{session_id}/bookings/{booking_id}",
        headers=headers,
        json={"course_id": course_id, "day": 3, "start_slot": 8},
    )

    resolved = client.get(
        f"/sessions/{session_id}/change-log",
        params={"resolved": "true"},
        headers=headers,
    )
    assert resolved.status_code == 200
    rows = resolved.json()["rows"]
    assert rows
    entry_id = rows[0]["entry_id"]
    assert entry_id is not None

    note = client.patch(
        f"/sessions/{session_id}/change-log/entries/{entry_id}/notes",
        headers=headers,
        json={"booking_id": booking_id, "note": "Approved move"},
    )
    assert note.status_code == 200

    again = client.get(
        f"/sessions/{session_id}/change-log",
        params={"resolved": "true"},
        headers=headers,
    ).json()
    assert any(r["note"] == "Approved move" for r in again["rows"])


def test_change_log_export(client: TestClient):
    _token, session_id, course_id, booking_id, headers = _seed(client)
    client.patch(
        f"/sessions/{session_id}/bookings/{booking_id}",
        headers=headers,
        json={"course_id": course_id, "day": 1, "start_slot": 4},
    )
    res = client.get(
        f"/sessions/{session_id}/change-log/export",
        params={"resolved": "true"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(res.content) > 1000


def test_health_reports_phase_six(client: TestClient):
    res = client.get("/health")
    assert res.json()["phase"] == 8

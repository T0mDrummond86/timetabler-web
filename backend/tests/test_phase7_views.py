"""Phase 7 — all regular and block timetable views."""
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
            "email": "phase7@example.com",
            "password": "password123",
            "name": "Phase Seven",
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


def test_day_view_readonly(client: TestClient):
    token, session_id = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    _seed(client, token, session_id)

    grid = client.get(
        f"/sessions/{session_id}/timetable",
        params={"view": "day", "day": 0},
        headers=headers,
    )
    assert grid.status_code == 200, grid.text
    data = grid.json()
    assert data["view"] == "day"
    assert data["column_kind"] == "staff"
    assert data["readonly"] is True


def test_unassigned_lecturer_view(client: TestClient):
    token, session_id = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    _seed(client, token, session_id)

    entities = client.get(
        f"/sessions/{session_id}/timetable-entities",
        params={"view": "unassigned_lecturer"},
        headers=headers,
    )
    assert entities.status_code == 200
    assert len(entities.json()) == 1

    grid = client.get(
        f"/sessions/{session_id}/timetable",
        params={"view": "unassigned_lecturer"},
        headers=headers,
    )
    assert grid.status_code == 200
    assert grid.json()["view"] == "unassigned_lecturer"


def test_course_semester_schedule(client: TestClient):
    token, session_id = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    seed = _seed(client, token, session_id)
    course_id = seed["course_id"]

    schedule = client.get(
        f"/sessions/{session_id}/course-semester-schedule",
        params={"course_id": course_id},
        headers=headers,
    )
    assert schedule.status_code == 200, schedule.text
    data = schedule.json()
    assert data["course_id"] == course_id
    assert len(data["rows"]) >= 1
    assert data["selected_semester_week"] == 1


def test_block_overview_empty(client: TestClient):
    token, session_id = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    _seed(client, token, session_id)

    overview = client.get(
        f"/sessions/{session_id}/block-overview",
        headers=headers,
    )
    assert overview.status_code == 200
    assert overview.json()["rows"] == []


def test_timetable_entities_all_regular_views(client: TestClient):
    token, session_id = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    _seed(client, token, session_id)

    for view in ("course", "staff", "room", "day", "course_semester", "co_teach"):
        res = client.get(
            f"/sessions/{session_id}/timetable-entities",
            params={"view": view},
            headers=headers,
        )
        assert res.status_code == 200, f"{view}: {res.text}"


def test_health_reports_phase_seven(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["phase"] == 8

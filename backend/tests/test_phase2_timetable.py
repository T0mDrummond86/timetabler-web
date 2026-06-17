"""Phase 2 read-only timetable grid API."""
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


def _register(client: TestClient) -> tuple[str, int, int]:
    reg = client.post(
        "/auth/register",
        json={
            "username": "grid",
            "password": "password123",
            "name": "Grid Tester",
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
    return token, org_id, session_id


def test_timetable_grid_with_demo_seed(client: TestClient):
    token, _org_id, session_id = _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    seed = client.post(f"/sessions/{session_id}/seed-demo", headers=headers)
    assert seed.status_code == 200
    assert seed.json()["booking_count"] == 2

    courses = client.get(f"/sessions/{session_id}/courses", headers=headers)
    assert courses.status_code == 200
    assert len(courses.json()) == 1
    course_id = courses.json()[0]["id"]

    grid = client.get(
        f"/sessions/{session_id}/timetable",
        params={"course_id": course_id},
        headers=headers,
    )
    assert grid.status_code == 200, grid.text
    data = grid.json()
    assert data["course_code"] == "Demo GrpA"
    assert len(data["bookings"]) == 2
    assert data["num_slots"] == 28
    assert data["days"][0] == "Monday"
    assert all("fill_colour" in b for b in data["bookings"])

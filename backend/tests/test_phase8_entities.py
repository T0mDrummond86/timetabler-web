"""Phase 8 — entity editors (qualifications, block delivery)."""
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
            "email": "phase8@example.com",
            "password": "password123",
            "name": "Phase Eight",
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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_patch_qualification(client: TestClient):
    token, session_id = _register(client)
    headers = _headers(token)
    client.post(f"/sessions/{session_id}/seed-demo", headers=headers)

    quals = client.get(f"/sessions/{session_id}/qualifications", headers=headers)
    assert quals.status_code == 200
    qual_id = quals.json()[0]["id"]

    patch = client.patch(
        f"/sessions/{session_id}/qualifications/{qual_id}",
        headers=headers,
        json={"name": "Updated qual name", "num_groups": 2, "schedule_period": "night"},
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["name"] == "Updated qual name"
    assert body["num_groups"] == 2
    assert body["schedule_period"] == "night"


def test_create_block_and_block_delivery_timetable(client: TestClient):
    token, session_id = _register(client)
    headers = _headers(token)
    client.post(f"/sessions/{session_id}/seed-demo", headers=headers)

    quals = client.get(f"/sessions/{session_id}/qualifications", headers=headers).json()
    qual_id = quals[0]["id"]

    missing = client.get(
        f"/sessions/{session_id}/timetable",
        headers=headers,
        params={"view": "block_delivery"},
    )
    assert missing.status_code == 422
    assert "course_id" in missing.json()["detail"].lower()

    create = client.post(
        f"/sessions/{session_id}/qualifications/{qual_id}/create-block",
        headers=headers,
    )
    assert create.status_code == 200, create.text
    block = create.json()
    assert block["course_id"]
    assert block["course_code"]

    panel = client.get(
        f"/sessions/{session_id}/block-delivery-panel",
        headers=headers,
        params={"qualification_id": qual_id, "course_id": block["course_id"]},
    )
    assert panel.status_code == 200, panel.text
    assert panel.json()["selected_course_id"] == block["course_id"]

    grid = client.get(
        f"/sessions/{session_id}/timetable",
        headers=headers,
        params={
            "view": "block_delivery",
            "course_id": block["course_id"],
            "block_week_index": 1,
        },
    )
    assert grid.status_code == 200, grid.text
    assert grid.json()["view"] == "block_delivery"


def test_duplicate_block_group(client: TestClient):
    token, session_id = _register(client)
    headers = _headers(token)
    client.post(f"/sessions/{session_id}/seed-demo", headers=headers)

    qual_id = client.get(f"/sessions/{session_id}/qualifications", headers=headers).json()[0]["id"]
    create = client.post(
        f"/sessions/{session_id}/qualifications/{qual_id}/create-block",
        headers=headers,
    )
    assert create.status_code == 200, create.text
    block = create.json()

    exp = client.get(f"/sessions/{session_id}/export/json", headers=headers).json()
    qual = next(q for q in exp["qualifications"] if q["id"] == qual_id)
    assert qual["delivery_mode"] == "block"

    dup = client.post(
        f"/sessions/{session_id}/block-groups/{block['course_id']}/duplicate",
        headers=headers,
        json={"new_code": "Demo Qualification Blk GrpB"},
    )
    assert dup.status_code == 200, dup.text
    assert dup.json()["course_code"] == "Demo Qualification Blk GrpB"


def test_qualification_detail_and_group_sync(client: TestClient):
    token, session_id = _register(client)
    headers = _headers(token)
    client.post(f"/sessions/{session_id}/seed-demo", headers=headers)

    created = client.post(
        f"/sessions/{session_id}/qualifications",
        headers=headers,
        json={"name": "Sync Test Qual"},
    )
    assert created.status_code == 201
    qual_id = created.json()["id"]

    detail = client.get(
        f"/sessions/{session_id}/qualifications/{qual_id}/detail",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["name"] == "Sync Test Qual"
    assert "schedule_summary" in body

    patch = client.patch(
        f"/sessions/{session_id}/qualifications/{qual_id}",
        headers=headers,
        json={"num_groups": 2},
    )
    assert patch.status_code == 200, patch.text

    detail2 = client.get(
        f"/sessions/{session_id}/qualifications/{qual_id}/detail",
        headers=headers,
    )
    assert detail2.status_code == 200
    assert len(detail2.json()["regular_groups"]) == 2


def test_staff_hours_table(client: TestClient):
    token, session_id = _register(client)
    headers = _headers(token)
    client.post(f"/sessions/{session_id}/seed-demo", headers=headers)

    table = client.get(f"/sessions/{session_id}/staff/hours-table", headers=headers)
    assert table.status_code == 200, table.text
    rows = table.json()
    assert len(rows) >= 1
    row = rows[0]
    assert "variance_category" in row
    assert "total_hours" in row
    assert "preferences_first" in row


def test_staff_preferences_and_online_students(client: TestClient):
    token, session_id = _register(client)
    headers = _headers(token)
    client.post(f"/sessions/{session_id}/seed-demo", headers=headers)

    staff_id = client.get(f"/sessions/{session_id}/staff", headers=headers).json()[0]["id"]

    prefs = client.put(
        f"/sessions/{session_id}/staff/{staff_id}/preferences",
        headers=headers,
        json={"first": ["Demo Unit"], "second": [], "third": []},
    )
    assert prefs.status_code == 200, prefs.text

    detail = client.get(f"/sessions/{session_id}/staff/{staff_id}/detail", headers=headers)
    assert detail.status_code == 200
    assert "Demo Unit" in detail.json()["preferences"]["first"]


def test_create_qualification(client: TestClient):
    token, session_id = _register(client)
    headers = _headers(token)

    created = client.post(
        f"/sessions/{session_id}/qualifications",
        headers=headers,
        json={"name": "New qualification"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "New qualification"

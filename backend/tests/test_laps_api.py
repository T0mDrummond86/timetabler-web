"""LAP creation API tests."""
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

LAP_TEMPLATE = Path("/Users/tomdrummond/Documents/apps/FormFiller-Innerrer/templates/lap_template.docx")


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth_headers(client: TestClient, username: str, org_name: str) -> tuple[dict[str, str], int]:
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "name": "LAP Tester",
            "organization_name": org_name,
        },
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org_id = client.get("/orgs", headers=headers).json()[0]["id"]
    session_id = client.get(f"/orgs/{org_id}/sessions", headers=headers).json()[0]["id"]
    return headers, session_id


@pytest.mark.skipif(not LAP_TEMPLATE.is_file(), reason="lap_template.docx not available")
def test_lap_upload_list_and_download(client: TestClient):
    headers, session_id = _auth_headers(client, "lap@test.example", "LAP Org")
    client.post(f"/sessions/{session_id}/seed-demo", headers=headers)
    units = client.get(f"/sessions/{session_id}/units", headers=headers).json()
    assert units
    unit_id = units[0]["id"]
    lap_bytes = LAP_TEMPLATE.read_bytes()

    up = client.post(
        f"/sessions/{session_id}/laps/{unit_id}",
        headers=headers,
        files={"file": ("intro.docx", lap_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert up.status_code == 204, up.text

    listing = client.get(f"/sessions/{session_id}/laps", headers=headers).json()
    row = next(r for r in listing["rows"] if r["unit_id"] == unit_id)
    assert row["has_lap"] is True
    assert row["original_filename"] == "intro.docx"

    dl = client.get(f"/sessions/{session_id}/laps/{unit_id}/download", headers=headers)
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"

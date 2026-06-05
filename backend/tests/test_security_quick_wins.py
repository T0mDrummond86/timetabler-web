"""Security quick-wins: config guards, upload cap, auth limits, cross-tenant spot checks."""
from __future__ import annotations

import io
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
os.environ["ENVIRONMENT"] = "development"

from timetable.core.models import Base  # noqa: E402
from timetable.core.tenancy_models import TimetableSession  # noqa: E402, F401

from app.config import Settings, validate_settings  # noqa: E402
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


def _register(client: TestClient, email: str, org_name: str) -> tuple[str, int, int]:
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "name": "Tester",
            "organization_name": org_name,
        },
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    orgs = client.get("/orgs", headers={"Authorization": f"Bearer {token}"}).json()
    org_id = orgs[0]["id"]
    sessions = client.get(f"/orgs/{org_id}/sessions", headers={"Authorization": f"Bearer {token}"}).json()
    session_id = sessions[0]["id"]
    return token, org_id, session_id


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_production_rejects_default_jwt_secret():
    cfg = Settings(environment="production", jwt_secret="change-me-in-production", auto_create_tables=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_settings(cfg)


def test_production_rejects_auto_create_tables():
    cfg = Settings(
        environment="production",
        jwt_secret="a-very-long-random-production-secret-value",
        auto_create_tables=True,
    )
    with pytest.raises(RuntimeError, match="AUTO_CREATE_TABLES"):
        validate_settings(cfg)


def test_openapi_hidden_in_production(monkeypatch):
    from app import main as main_mod

    monkeypatch.setattr(main_mod.settings, "environment", "production")
    monkeypatch.setattr(main_mod.settings, "jwt_secret", "a-very-long-random-production-secret-value")
    monkeypatch.setattr(main_mod.settings, "auto_create_tables", False)
    assert main_mod.settings.expose_api_docs is False


def test_seed_demo_disabled_in_production(client: TestClient, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    token, _org_id, session_id = _register(client, "seed@example.com", "Seed Org")
    resp = client.post(f"/sessions/{session_id}/seed-demo", headers=_headers(token))
    assert resp.status_code == 404


def test_registration_disabled(client: TestClient, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "allow_registration", False)
    resp = client.post(
        "/auth/register",
        json={
            "email": "blocked@example.com",
            "password": "password123",
            "name": "Blocked",
            "organization_name": "Blocked Org",
        },
    )
    assert resp.status_code == 403


def test_upload_rejects_oversized_file(client: TestClient, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    token, _org_id, session_id = _register(client, "upload@example.com", "Upload Org")
    big = b"x" * 2048
    resp = client.post(
        f"/sessions/{session_id}/import",
        headers=_headers(token),
        files={"file": ("big.xlsx", io.BytesIO(big), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 413


def test_cross_org_session_access_denied(client: TestClient):
    token_a, _org_a, session_a = _register(client, "alice@example.com", "Org Alpha")
    token_b, _org_b, session_b = _register(client, "bob@example.com", "Org Beta")
    assert session_a != session_b

    headers_a = _headers(token_a)

    timetable = client.get(f"/sessions/{session_b}/timetable", headers=headers_a)
    assert timetable.status_code == 404

    import_resp = client.post(
        f"/sessions/{session_b}/import",
        headers=headers_a,
        files={"file": ("empty.xlsx", io.BytesIO(b""), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert import_resp.status_code in (400, 404, 413)

    export_admin = client.get(f"/sessions/{session_b}/export/admin", headers=headers_a)
    assert export_admin.status_code == 404

    booking = client.post(
        f"/sessions/{session_b}/bookings",
        headers=headers_a,
        json={
            "course_id": 1,
            "unit_id": 1,
            "day": 0,
            "start_slot": 0,
            "end_slot": 1,
        },
    )
    assert booking.status_code == 404


def test_cross_org_global_session_members_denied(client: TestClient):
    token_a, org_a, session_a = _register(client, "carol@example.com", "Org Carol")
    token_b, org_b, session_b = _register(client, "dave@example.com", "Org Dave")
    headers_b = _headers(token_b)

    g = client.post(
        f"/orgs/{org_b}/global-sessions",
        headers=headers_b,
        json={"name": "Dave Global"},
    )
    assert g.status_code == 201
    global_id = g.json()["id"]

    put = client.put(
        f"/global-sessions/{global_id}/members",
        headers=_headers(token_a),
        json={"timetable_session_ids": [session_a]},
    )
    assert put.status_code == 404

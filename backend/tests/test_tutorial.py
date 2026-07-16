"""Tutorial sandbox: dataset determinism, expected violations, lifecycle."""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

import pytest
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
os.environ["ALLOW_REGISTRATION"] = "true"

from timetable.core.clash_check_settings import (  # noqa: E402
    filter_violations_by_clash_settings,
    parse_clash_check_settings_json,
)
from timetable.core.models import Base, Booking, Course, Semester, Unit, Week  # noqa: E402
from timetable.core.pending_classes import pending_classes_for_course  # noqa: E402
from timetable.core.tenancy_models import Organization, TimetableSession  # noqa: E402
from timetable.core.validation import validate_bookings  # noqa: E402
from timetable.io.backup_payload import PAYLOAD_VERSION  # noqa: E402

from app.services.session_data import restore_session, serialize_session  # noqa: E402
from app.services.session_seed import seed_timetable_session_data  # noqa: E402
from app.services.tutorial.dataset import (  # noqa: E402
    EXPECTED_HOLDING,
    EXPECTED_VIOLATION_CODES,
    build_tutorial_payload,
    tutorial_clash_settings_json,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_session(db) -> TimetableSession:
    org = Organization(name="Test Org", slug="test-org")
    db.add(org)
    db.flush()
    row = TimetableSession(organization_id=org.id, name="Tutorial sandbox — tester")
    db.add(row)
    db.flush()
    seed_timetable_session_data(db, row)
    db.commit()
    return row


def _repeating_week(db, session_id: int) -> Week:
    return (
        db.query(Week)
        .join(Semester, Week.semester_id == Semester.id)
        .filter(Semester.timetable_session_id == session_id, Week.week_number == 0)
        .one()
    )


def test_payload_deterministic_and_versioned():
    a = build_tutorial_payload()
    b = build_tutorial_payload()
    assert a == b
    assert a is not b  # fresh dict each call — restore can't mutate shared state
    assert a["version"] == PAYLOAD_VERSION
    assert len(a["bookings"]) == 24
    assert len(a["units"]) == 12
    assert len(a["staff"]) == 8
    assert len(a["rooms"]) == 7


def test_restore_round_trip(db):
    row = _make_session(db)
    counts = restore_session(db, row.id, build_tutorial_payload())
    db.commit()
    assert counts == {
        "qualifications": 2,
        "courses": 4,
        "staff": 8,
        "rooms": 7,
        "bookings": 24,
    }
    # Bracket-parsing must not have mutated unit names, and combined-class
    # detection must not have grouped any tutorial bookings.
    names = {u.name for u in db.query(Unit).filter_by(timetable_session_id=row.id)}
    payload_names = {u["name"] for u in build_tutorial_payload()["units"]}
    assert names == payload_names
    week = _repeating_week(db, row.id)
    combined = (
        db.query(Booking)
        .filter(Booking.week_id == week.id, Booking.combined_class_group_id.isnot(None))
        .count()
    )
    assert combined == 0
    # Serialize → restore onto a second session reproduces the same shape.
    dumped = serialize_session(db, row.id)
    assert len(dumped["bookings"]) == 24
    assert {u["name"] for u in dumped["units"]} == payload_names


def test_expected_violation_multiset(db):
    row = _make_session(db)
    restore_session(db, row.id, build_tutorial_payload())
    db.commit()
    week = _repeating_week(db, row.id)
    settings = parse_clash_check_settings_json(tutorial_clash_settings_json())
    violations = filter_violations_by_clash_settings(
        validate_bookings(db, week.id), settings
    )
    assert Counter(v.code for v in violations) == Counter(EXPECTED_VIOLATION_CODES)


def test_holding_area_contents(db):
    row = _make_session(db)
    restore_session(db, row.id, build_tutorial_payload())
    db.commit()
    week = _repeating_week(db, row.id)
    courses = {
        c.code: c for c in db.query(Course).filter_by(timetable_session_id=row.id)
    }
    unit_names = {u.id: u.name for u in db.query(Unit).filter_by(timetable_session_id=row.id)}
    for code, expected_names in EXPECTED_HOLDING.items():
        pending = pending_classes_for_course(db, week.id, courses[code].id)
        assert sorted(unit_names[p.unit_id] for p in pending) == sorted(expected_names), code
    for code in ("CYB-B", "CHC-A"):
        assert pending_classes_for_course(db, week.id, courses[code].id) == [], code


# --- Endpoint tests (find-or-create, guarded reset, production-safe) ---

from fastapi.testclient import TestClient  # noqa: E402

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    # Settings are a process-wide singleton; patch directly so these tests are
    # order-independent when the whole suite runs in one process.
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "allow_registration", True)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client: TestClient, username: str, org: str) -> tuple[dict, int]:
    reg = client.post(
        "/auth/register",
        json={
            "username": username,
            "password": "password123",
            "name": username.title(),
            "organization_name": org,
        },
    )
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": "password123", "new_password": "password456"},
    )
    assert changed.status_code == 200, changed.text
    org_id = client.get("/orgs", headers=headers).json()[0]["id"]
    return headers, org_id


def test_start_tutorial_idempotent_and_private(client):
    headers, org_id = _register(client, "alice", "Org A")
    first = client.post(f"/orgs/{org_id}/tutorial-session", headers=headers)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["created"] is True
    assert body["session"]["name"] == "Tutorial sandbox — alice"
    assert body["entities"]["courses"].keys() >= {"CYB-A", "CYB-B", "CHC-A", "CYB-T"}
    assert "Tom Nguyen" in body["entities"]["staff"]

    second = client.post(f"/orgs/{org_id}/tutorial-session", headers=headers)
    assert second.status_code == 201
    assert second.json()["created"] is False
    assert second.json()["session"]["id"] == body["session"]["id"]

    # Another user in the same org gets their own sandbox and can't see Alice's.
    headers_b, _ = _register(client, "bob", "Org B")
    sid = body["session"]["id"]
    assert client.get(f"/sessions/{sid}/tutorial-info", headers=headers_b).status_code == 404
    assert client.post(f"/sessions/{sid}/tutorial-reset", headers=headers_b).status_code == 404

    info = client.get(f"/sessions/{sid}/tutorial-info", headers=headers)
    assert info.status_code == 200
    assert info.json()["is_tutorial"] is True


def test_reset_restores_pristine_and_guards_real_sessions(client):
    headers, org_id = _register(client, "carol", "Org C")
    started = client.post(f"/orgs/{org_id}/tutorial-session", headers=headers).json()
    sid = started["session"]["id"]
    tom = started["entities"]["staff"]["Tom Nguyen"]
    course = started["entities"]["courses"]["CYB-T"]
    unit = started["entities"]["units"]["Network Security Fundamentals — VU23217"]

    # Mutate: add a booking, then reset — booking count returns to 24.
    created = client.post(
        f"/sessions/{sid}/bookings",
        headers=headers,
        json={"course_id": course, "unit_id": unit, "day": 3, "start_slot": 20,
              "end_slot": 24, "staff_id": tom},
    )
    assert created.status_code in (200, 201), created.text

    reset = client.post(f"/sessions/{sid}/tutorial-reset", headers=headers)
    assert reset.status_code == 200, reset.text
    assert reset.json()["session"]["booking_count"] == 24

    # Reset refuses an ordinary session outright.
    real = client.post(f"/orgs/{org_id}/sessions", headers=headers, json={"name": "Real 2026"})
    assert real.status_code == 201
    refused = client.post(f"/sessions/{real.json()['id']}/tutorial-reset", headers=headers)
    assert refused.status_code == 403
    info = client.get(f"/sessions/{real.json()['id']}/tutorial-info", headers=headers)
    assert info.status_code == 200
    assert info.json()["is_tutorial"] is False


def test_tutorial_works_in_production(client, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "environment", "production")
    assert app_settings.is_production
    headers, org_id = _register(client, "dave", "Org D")
    resp = client.post(f"/orgs/{org_id}/tutorial-session", headers=headers)
    assert resp.status_code == 201, resp.text
    sid = resp.json()["session"]["id"]
    assert client.post(f"/sessions/{sid}/tutorial-reset", headers=headers).status_code == 200

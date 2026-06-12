"""Week-level violation cache (Phase A)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parents[1]
DOMAIN = BACKEND.parent / "packages" / "domain"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(DOMAIN))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret"

from timetable.core.models import (  # noqa: E402
    Base,
    Booking,
    Course,
    Room,
    Semester,
    Staff,
    Unit,
    Week,
)
from timetable.core.tenancy_models import Organization, TimetableSession  # noqa: E402
from timetable.core.validation import validate_bookings  # noqa: E402

from app.services.session_seed import seed_timetable_session_data  # noqa: E402
from app.services.violation_cache import (  # noqa: E402
    clear_violation_cache_for_tests,
    filter_violations_for_bookings,
    get_week_violations,
    invalidate_week_violations,
    resolve_week_violations,
)


@pytest.fixture()
def db_session():
    clear_violation_cache_for_tests()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    org = Organization(name="Cache Org", slug="cache-org")
    session.add(org)
    session.flush()
    ts = TimetableSession(organization_id=org.id, name="Cache session")
    session.add(ts)
    session.flush()
    seed_timetable_session_data(session, ts)
    session.commit()
    yield session
    session.close()
    clear_violation_cache_for_tests()


def _week_id(session) -> int:
    sem = session.query(Semester).filter(Semester.timetable_session_id == session.query(TimetableSession).one().id).one()
    return session.query(Week).filter(Week.semester_id == sem.id, Week.week_number == 0).one().id


def _add_booking(
    session,
    *,
    week_id: int,
    day: int,
    start: int,
    end: int,
    room: Room | None = None,
) -> Booking:
    ts = session.query(TimetableSession).one()
    tag = f"{day}{start}{end}"
    course = Course(timetable_session_id=ts.id, code=f"C{tag}")
    unit = Unit(timetable_session_id=ts.id, name=f"Unit {tag}")
    staff = Staff(timetable_session_id=ts.id, name=f"Lecturer {tag}")
    if room is None:
        room = Room(
            timetable_session_id=ts.id,
            code=f"R{tag}",
            room_type="on-campus",
            capacity=24,
        )
        session.add(room)
    session.add_all([course, unit, staff])
    session.flush()
    booking = Booking(
        week_id=week_id,
        course_id=course.id,
        unit_id=unit.id,
        staff_id=staff.id,
        room_id=room.id,
        day=day,
        start_slot=start,
        end_slot=end,
    )
    session.add(booking)
    session.flush()
    return booking


def test_get_week_violations_uses_cache(db_session):
    week_id = _week_id(db_session)
    first = _add_booking(db_session, week_id=week_id, day=0, start=2, end=4)
    _add_booking(
        db_session,
        week_id=week_id,
        day=0,
        start=3,
        end=5,
        room=db_session.get(Room, first.room_id),
    )

    with patch("app.services.violation_cache.validate_bookings", wraps=validate_bookings) as mocked:
        first = get_week_violations(db_session, week_id)
        second = get_week_violations(db_session, week_id)

    assert mocked.call_count == 1
    assert len(first) == len(second)
    assert any(v.code == "room_double_booking" for v in first)


def test_invalidate_forces_recompute(db_session):
    week_id = _week_id(db_session)
    _add_booking(db_session, week_id=week_id, day=1, start=2, end=4)

    with patch("app.services.violation_cache.validate_bookings", wraps=validate_bookings) as mocked:
        get_week_violations(db_session, week_id)
        invalidate_week_violations(week_id)
        get_week_violations(db_session, week_id)

    assert mocked.call_count == 2


def test_filter_violations_for_bookings_matches_subset_rules(db_session):
    week_id = _week_id(db_session)
    a = _add_booking(db_session, week_id=week_id, day=2, start=2, end=4)
    b = _add_booking(
        db_session,
        week_id=week_id,
        day=2,
        start=3,
        end=5,
        room=db_session.get(Room, a.room_id),
    )
    all_v = get_week_violations(db_session, week_id)
    pair = next(v for v in all_v if v.code == "room_double_booking" and set(v.booking_ids) == {a.id, b.id})

    filtered = filter_violations_for_bookings(all_v, [a])
    assert pair not in filtered

    both = filter_violations_for_bookings(all_v, [a, b])
    assert pair in both


def test_resolve_week_violations_off_skips_validation(db_session):
    week_id = _week_id(db_session)
    with patch("app.services.violation_cache.validate_bookings", wraps=validate_bookings) as mocked:
        assert resolve_week_violations(db_session, week_id, "off") == []
        mocked.assert_not_called()


def test_resolve_week_violations_once_forces_fresh_pass(db_session):
    week_id = _week_id(db_session)
    _add_booking(db_session, week_id=week_id, day=1, start=2, end=4)
    get_week_violations(db_session, week_id)
    with patch("app.services.violation_cache.validate_bookings", wraps=validate_bookings) as mocked:
        resolve_week_violations(db_session, week_id, "once")
        assert mocked.call_count == 1


def test_build_course_timetable_clash_detect_off(db_session):
    from app.services.timetable_grid import build_course_timetable

    ts = db_session.query(TimetableSession).one()
    course = db_session.query(Course).filter(Course.timetable_session_id == ts.id).first()
    assert course is not None
    with patch("app.services.violation_cache.validate_bookings", wraps=validate_bookings) as mocked:
        grid = build_course_timetable(
            db_session,
            timetable_session_id=ts.id,
            course_id=course.id,
            clash_detect="off",
        )
        mocked.assert_not_called()
    assert grid["violations"] == []

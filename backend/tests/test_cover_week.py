"""Planning cover a week at a time.

Two behaviours worth pinning down: repeating the plan forward moves the *last*
week rather than everything listed, and the owed-hours pair shown against each
pending request runs cumulatively so a lecturer taking three covers sees the
debt come down three times.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DOMAIN = BACKEND.parent / "packages" / "domain"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(DOMAIN))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("AUTO_CREATE_TABLES", "false")
os.environ.setdefault("JWT_SECRET", "test-secret")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from timetable.core.models import Base, Booking, Course, Semester, Week  # noqa: E402
from timetable.core.tenancy_models import (  # noqa: E402
    CoverRequest,
    Organization,
    TimetableSession,
)

from app.services.cover_requests import (  # noqa: E402
    create_cover_request,
    duplicate_latest_week,
    list_cover_requests,
)

SID = 1
# An arbitrary Monday.
MON = _dt.date(2026, 3, 2)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    org = Organization(name="T", slug="t")
    session.add(org)
    session.flush()
    session.add(TimetableSession(id=SID, organization_id=org.id, name="S"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _req(db, *, booking_id: int, date: _dt.date, cover: str = "Ann", week: int | None = None):
    return create_cover_request(
        db,
        timetable_session_id=SID,
        booking_id=booking_id,
        cover_date=date.isoformat(),
        semester=1 if week is not None else None,
        week_number=week,
        day_label="Mon",
        time_label="09:00–11:00",
        group_name="GrpA",
        unit_name="Networking",
        room_code="A1",
        away_staff_name="Bo",
        cover_staff_id=None,
        cover_staff_name=cover,
    )


_next_booking = [0]


def _booking(db, slots: int) -> int:
    """A booking `slots` half-hours long — 2 slots to the hour."""
    _next_booking[0] += 1
    n = _next_booking[0]
    sem = db.query(Semester).first()
    if sem is None:
        sem = Semester(timetable_session_id=SID, name="S1", num_weeks=18)
        db.add(sem)
        db.flush()
    week = db.query(Week).first()
    if week is None:
        week = Week(semester_id=sem.id, week_number=0, label="Repeating")
        db.add(week)
        db.flush()
    course = Course(timetable_session_id=SID, code=f"C{n}")
    db.add(course)
    db.flush()
    row = Booking(
        week_id=week.id,
        course_id=course.id,
        day=0,
        start_slot=2,
        end_slot=2 + slots,
    )
    db.add(row)
    db.flush()
    return row.id


def _dates(db) -> list[str]:
    return sorted(
        r.cover_date.isoformat()
        for r in db.query(CoverRequest).filter_by(timetable_session_id=SID).all()
    )


class TestRepeatNextWeek:
    def test_copies_the_plan_forward_by_seven_days(self, db):
        _req(db, booking_id=1, date=MON)
        _req(db, booking_id=2, date=MON + _dt.timedelta(days=2))

        out = duplicate_latest_week(db, timetable_session_id=SID)

        assert out["created"] == 2
        assert out["week_beginning"] == (MON + _dt.timedelta(days=7)).isoformat()
        assert _dates(db) == [
            MON.isoformat(),
            (MON + _dt.timedelta(days=2)).isoformat(),
            (MON + _dt.timedelta(days=7)).isoformat(),
            (MON + _dt.timedelta(days=9)).isoformat(),
        ]

    def test_pressing_twice_gives_two_further_weeks_not_a_doubling(self, db):
        _req(db, booking_id=1, date=MON)

        duplicate_latest_week(db, timetable_session_id=SID)
        duplicate_latest_week(db, timetable_session_id=SID)

        # One class a week for three weeks — not the four a re-copy would give.
        assert _dates(db) == [
            MON.isoformat(),
            (MON + _dt.timedelta(days=7)).isoformat(),
            (MON + _dt.timedelta(days=14)).isoformat(),
        ]

    def test_carries_the_cover_lecturer_and_advances_the_week_number(self, db):
        _req(db, booking_id=1, date=MON, cover="Ann", week=3)

        duplicate_latest_week(db, timetable_session_id=SID)

        copy = (
            db.query(CoverRequest)
            .filter(CoverRequest.cover_date == MON + _dt.timedelta(days=7))
            .one()
        )
        assert copy.cover_staff_name == "Ann"
        assert copy.week_number == 4
        assert copy.unit_name == "Networking"

    def test_a_week_already_partly_copied_is_topped_up_not_duplicated(self, db):
        _req(db, booking_id=1, date=MON)
        _req(db, booking_id=2, date=MON)
        # One of the two already exists in the following week.
        _req(db, booking_id=1, date=MON + _dt.timedelta(days=7))

        # The latest week is now the second one, holding only booking 1.
        out = duplicate_latest_week(db, timetable_session_id=SID)

        assert out["created"] == 1
        assert len(_dates(db)) == 4

    def test_refuses_when_nothing_has_a_date(self, db):
        create_cover_request(
            db,
            timetable_session_id=SID,
            booking_id=1,
            cover_date=None,
            semester=None,
            week_number=None,
            day_label="Mon",
            time_label="09:00–11:00",
            group_name="",
            unit_name="",
            room_code="",
            away_staff_name="",
            cover_staff_id=None,
            cover_staff_name="",
        )

        with pytest.raises(ValueError, match="Nothing to duplicate"):
            duplicate_latest_week(db, timetable_session_id=SID)


class TestSameClassDifferentWeeks:
    def test_the_same_class_can_be_covered_in_two_weeks(self, db):
        """The date is part of a request's identity, not just semester/week.

        Without a calendar loaded, semester and week are null, so the date is
        the only thing that tells one week's cover from the next.
        """
        _req(db, booking_id=1, date=MON)
        _req(db, booking_id=1, date=MON + _dt.timedelta(days=7))

        assert len(_dates(db)) == 2

    def test_reassigning_the_same_class_in_the_same_week_updates_in_place(self, db):
        _req(db, booking_id=1, date=MON, cover="Ann")
        _req(db, booking_id=1, date=MON, cover="Bo")

        rows = db.query(CoverRequest).filter_by(timetable_session_id=SID).all()
        assert len(rows) == 1
        assert rows[0].cover_staff_name == "Bo"


class TestOwedHoursColumns:
    def test_no_figures_when_the_session_has_no_workspace(self, db):
        """No workspace means no cover log, so there is no ledger to report."""
        _req(db, booking_id=1, date=MON, cover="Ann")

        [row] = list_cover_requests(db, timetable_session_id=SID)

        assert row["hours_owed_before"] is None
        assert row["hours_owed_after"] is None

    def test_figures_run_cumulatively_for_one_lecturer(self, db, monkeypatch):
        # Ann is 5 hours behind; each of these covers is 2 hours (4 slots).
        monkeypatch.setattr(
            "app.services.cover_lecturers._shortfall_by_lecturer",
            lambda db, sid: {"ann": 5.0},
        )
        a, b, c = _booking(db, 4), _booking(db, 4), _booking(db, 4)
        _req(db, booking_id=a, date=MON, cover="Ann")
        _req(db, booking_id=b, date=MON + _dt.timedelta(days=1), cover="Ann")
        _req(db, booking_id=c, date=MON + _dt.timedelta(days=2), cover="Ann")

        rows = list_cover_requests(db, timetable_session_id=SID)

        assert [r["hours"] for r in rows] == [2.0, 2.0, 2.0]
        # The debt comes down once per cover rather than the same figure thrice.
        assert [r["hours_owed_before"] for r in rows] == [5.0, 3.0, 1.0]
        assert [r["hours_owed_after"] for r in rows] == [3.0, 1.0, 0.0]

    def test_a_second_lecturer_keeps_their_own_running_total(self, db, monkeypatch):
        monkeypatch.setattr(
            "app.services.cover_lecturers._shortfall_by_lecturer",
            lambda db, sid: {"ann": 4.0, "bo": 1.0},
        )
        a, b = _booking(db, 4), _booking(db, 4)
        _req(db, booking_id=a, date=MON, cover="Ann")
        _req(db, booking_id=b, date=MON, cover="Bo")

        rows = list_cover_requests(db, timetable_session_id=SID)

        assert [r["hours_owed_before"] for r in rows] == [4.0, 1.0]
        # Bo owes less than the job is long; the debt floors at nothing owed.
        assert [r["hours_owed_after"] for r in rows] == [2.0, 0.0]

    def test_an_unassigned_request_shows_no_figures(self, db, monkeypatch):
        monkeypatch.setattr(
            "app.services.cover_lecturers._shortfall_by_lecturer",
            lambda db, sid: {"ann": 4.0},
        )
        _req(db, booking_id=_booking(db, 4), date=MON, cover="")

        [row] = list_cover_requests(db, timetable_session_id=SID)

        assert row["hours_owed_before"] is None
        assert row["hours_owed_after"] is None

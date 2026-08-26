"""Hours set by hand on a pending cover request.

Cover hours come from the class being covered, which is right almost every
time. It is wrong when the arrangement and the timetable disagree -- someone
taking only the back half of a three-hour class, a session that finished early,
two people splitting one cover. The override exists for those.

The figure the panel previews has to be the figure that reaches the log, so the
tests below follow one adjusted request all the way through: the listing, the
running debt, the copy forward, and the push to the global log.
"""
from __future__ import annotations

import datetime as dt
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

from timetable.core.models import Base, Booking, Course, Semester, Staff, Unit, Week  # noqa: E402
from timetable.core.tenancy_models import (  # noqa: E402
    CoverLogEntry,
    CoverRequest,
    GlobalSession,
    GlobalSessionMember,
    Organization,
    TimetableSession,
)

from app.services.cover_requests import (  # noqa: E402
    duplicate_request_next_week,
    list_cover_requests,
    promote_cover_request,
    update_cover_request,
)

SID = 1
GSID = 10


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    s.add(Organization(id=1, name="T", slug="t"))
    s.flush()
    s.add(TimetableSession(id=SID, organization_id=1, name="Joondalup"))
    s.add(GlobalSession(id=GSID, organization_id=1, name="WS"))
    s.flush()
    s.add(GlobalSessionMember(global_session_id=GSID, timetable_session_id=SID))
    sem = Semester(timetable_session_id=SID, name="S1")
    s.add(sem)
    s.flush()
    s.add(Week(id=1, semester_id=sem.id, week_number=0))
    s.commit()
    try:
        yield s
    finally:
        s.close()


def _booking(db, *, start: int, end: int) -> Booking:
    """A booking of a known length -- 2 slots to the hour."""
    course = Course(timetable_session_id=SID, code="Cert IV GrpA")
    unit = Unit(timetable_session_id=SID, name="Threat data", length_slots=end - start)
    staff = Staff(timetable_session_id=SID, name="A. Rivers", fte=1.0)
    db.add_all([course, unit, staff])
    db.flush()
    b = Booking(
        week_id=1,
        course_id=course.id,
        unit_id=unit.id,
        staff_id=staff.id,
        day=0,
        start_slot=start,
        end_slot=end,
    )
    db.add(b)
    db.flush()
    return b


def _request(db, booking: Booking | None, *, hours: float | None = None) -> CoverRequest:
    r = CoverRequest(
        timetable_session_id=SID,
        booking_id=booking.id if booking else None,
        cover_date=dt.date(2026, 3, 2),
        week_number=3,
        day_label="Mon",
        time_label="09:00–12:00",
        unit_name="Threat data",
        away_staff_name="A. Rivers",
        cover_staff_name="B. Nakamura",
        hours=hours,
    )
    db.add(r)
    db.commit()
    return r


def _listed(db) -> list[dict]:
    return list_cover_requests(db, timetable_session_id=SID)


class TestDefaultsToTheClassLength:
    def test_hours_come_from_the_booking(self, db):
        _request(db, _booking(db, start=2, end=8))  # 6 slots = 3 hours

        row = _listed(db)[0]

        assert row["hours"] == pytest.approx(3.0)
        # Nothing was set by hand, and the panel needs to know that.
        assert row["hours_manual"] is None

    def test_a_request_whose_booking_is_gone_has_no_hours(self, db):
        _request(db, None)

        assert _listed(db)[0]["hours"] is None


class TestSettingHoursByHand:
    def test_an_override_replaces_the_derived_figure(self, db):
        r = _request(db, _booking(db, start=2, end=8))  # 3 hours

        update_cover_request(db, timetable_session_id=SID, request_id=r.id, hours=1.5)

        row = _listed(db)[0]
        assert row["hours"] == pytest.approx(1.5)
        assert row["hours_manual"] == pytest.approx(1.5)

    def test_clearing_it_goes_back_to_the_class_length(self, db):
        r = _request(db, _booking(db, start=2, end=8), hours=1.5)

        update_cover_request(db, timetable_session_id=SID, request_id=r.id, hours=None)

        row = _listed(db)[0]
        assert row["hours"] == pytest.approx(3.0)
        assert row["hours_manual"] is None

    def test_editing_something_else_leaves_the_override_alone(self, db):
        r = _request(db, _booking(db, start=2, end=8), hours=1.5)

        # Changing the cover lecturer must not quietly reset the hours: the
        # caller said nothing about them.
        update_cover_request(
            db,
            timetable_session_id=SID,
            request_id=r.id,
            cover_staff_name="C. Okonkwo",
        )

        assert _listed(db)[0]["hours"] == pytest.approx(1.5)

    def test_hours_can_be_zero(self, db):
        # A cover that turned out not to be needed, kept for the record.
        r = _request(db, _booking(db, start=2, end=8))

        update_cover_request(db, timetable_session_id=SID, request_id=r.id, hours=0)

        assert _listed(db)[0]["hours"] == pytest.approx(0.0)

    @pytest.mark.parametrize("bad", [-1, -0.5, 25, 100])
    def test_nonsense_figures_are_refused(self, db, bad):
        r = _request(db, _booking(db, start=2, end=8))

        with pytest.raises(ValueError):
            update_cover_request(db, timetable_session_id=SID, request_id=r.id, hours=bad)


class TestTheDebtPreviewFollowsTheOverride:
    def _under_hours_cover_lecturer(self, db) -> None:
        # 1.0 FTE -> 21 lecturing hours, 20 carried -> 1.0 short -> owes 20.
        db.add(
            Staff(timetable_session_id=SID, name="B. Nakamura", fte=1.0, supervision_hours=20.0)
        )
        db.commit()

    def test_an_adjusted_job_pays_back_the_adjusted_amount(self, db):
        self._under_hours_cover_lecturer(db)
        r = _request(db, _booking(db, start=2, end=8))  # 3 hours

        before = _listed(db)[0]
        assert before["hours_owed_before"] == pytest.approx(20.0)
        assert before["hours_owed_after"] == pytest.approx(17.0)

        update_cover_request(db, timetable_session_id=SID, request_id=r.id, hours=1.0)

        after = _listed(db)[0]
        # One hour credited, not three -- otherwise the panel would promise a
        # payback the log then contradicts.
        assert after["hours_owed_after"] == pytest.approx(19.0)


class TestItReachesTheLog:
    def test_the_logged_entry_carries_the_adjusted_hours(self, db):
        r = _request(db, _booking(db, start=2, end=8), hours=1.5)

        promote_cover_request(db, timetable_session_id=SID, request_id=r.id)

        entry = db.query(CoverLogEntry).one()
        assert entry.hours == pytest.approx(1.5)
        assert db.query(CoverRequest).count() == 0

    def test_without_an_override_the_class_length_is_logged(self, db):
        r = _request(db, _booking(db, start=2, end=8))

        promote_cover_request(db, timetable_session_id=SID, request_id=r.id)

        assert db.query(CoverLogEntry).one().hours == pytest.approx(3.0)


class TestRepeatingKeepsIt:
    def test_next_week_inherits_the_adjusted_hours(self, db):
        r = _request(db, _booking(db, start=2, end=8), hours=1.5)

        duplicate_request_next_week(db, timetable_session_id=SID, request_id=r.id)

        copy = (
            db.query(CoverRequest)
            .filter(CoverRequest.cover_date == dt.date(2026, 3, 9))
            .one()
        )
        # The same arrangement a week later means the same adjusted hours.
        assert copy.hours == pytest.approx(1.5)

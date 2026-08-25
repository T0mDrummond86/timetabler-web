"""Two small behaviours that were each surprising in their own way.

A double-session class placed in one go already gave both halves the same
lecturer and room, because both came from the same call. The half added
*later* did not -- it took whatever that call happened to carry, which for a
fresh drag from the holding area is nothing. Same class, same group, and yet
the second sitting arrived unstaffed.

And repeating cover forward used to work a week at a time. Absences do not
line up like that: one class may need three weeks while the rest of the plan
is a single day.
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
from timetable.core.double_session import session_part_durations  # noqa: E402
from timetable.core.tenancy_models import (  # noqa: E402
    CoverRequest,
    Organization,
    TimetableSession,
)

from app.services.booking_mutations import create_booking  # noqa: E402
from app.services.cover_requests import duplicate_request_next_week  # noqa: E402

SID = 1


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
    s.add(TimetableSession(id=SID, organization_id=1, name="S"))
    sem = Semester(timetable_session_id=SID, name="S1")
    s.add(sem)
    s.flush()
    # week_number 0 is the repeating-week template get_repeating_week looks for.
    s.add(Week(id=1, semester_id=sem.id, week_number=0))
    s.commit()
    try:
        yield s
    finally:
        s.close()


def _double_unit(db, *, total_slots: int, first_slots: int | None) -> Unit:
    u = Unit(
        timetable_session_id=SID,
        name="Design and implement a server solution",
        length_slots=total_slots,
        double_session=1,
        double_session_first_slots=first_slots,
    )
    db.add(u)
    db.flush()
    return u


class TestFirstSessionLength:
    """The split is whatever was asked for, not a forced half."""

    def test_an_uneven_split_is_honoured(self, db):
        # A 3-hour class split 2.5 + 0.5 -- the case the old cap refused.
        unit = _double_unit(db, total_slots=6, first_slots=5)
        assert session_part_durations(unit) == (5, 1)

    def test_a_first_half_longer_than_the_class_falls_back(self, db):
        # Nonsense input still has to produce two sittings.
        unit = _double_unit(db, total_slots=6, first_slots=6)
        first, second = session_part_durations(unit)
        assert first + second == 6
        assert second >= 1

    def test_no_stated_split_halves_it(self, db):
        unit = _double_unit(db, total_slots=6, first_slots=None)
        assert session_part_durations(unit) == (3, 3)


class TestSecondSittingInheritsStaffAndRoom:
    def _setup(self, db):
        course = Course(timetable_session_id=SID, code="Cert IV GrpA")
        staff = Staff(timetable_session_id=SID, name="A. Rivers", fte=1.0)
        room = Room(timetable_session_id=SID, code="B2.14", capacity=25)
        unit = _double_unit(db, total_slots=6, first_slots=4)
        db.add_all([course, staff, room])
        db.flush()
        db.commit()
        return course, staff, room, unit

    def test_placed_in_one_go_both_halves_match(self, db):
        course, staff, room, unit = self._setup(db)
        create_booking(
            db,
            timetable_session_id=SID,
            course_id=course.id,
            unit_id=unit.id,
            staff_id=staff.id,
            room_id=room.id,
            day=0,
            start_slot=2,
            end_slot=8,
        )
        parts = {b.session_part: b for b in db.query(Booking).all()}
        assert set(parts) == {1, 2}
        assert parts[2].staff_id == staff.id
        assert parts[2].room_id == room.id

    def test_a_second_sitting_added_later_follows_the_first(self, db):
        course, staff, room, unit = self._setup(db)
        # Part one, staffed.
        db.add(
            Booking(
                week_id=1,
                course_id=course.id,
                unit_id=unit.id,
                staff_id=staff.id,
                room_id=room.id,
                day=0,
                start_slot=2,
                end_slot=6,
                session_part=1,
            )
        )
        db.commit()

        # Part two dropped in afterwards, naming neither lecturer nor room --
        # which is exactly what a drag from the holding area sends.
        create_booking(
            db,
            timetable_session_id=SID,
            course_id=course.id,
            unit_id=unit.id,
            staff_id=None,
            room_id=None,
            day=1,
            start_slot=2,
            end_slot=4,
        )

        part2 = db.query(Booking).filter(Booking.session_part == 2).one()
        assert part2.staff_id == staff.id
        assert part2.room_id == room.id

    def test_an_explicit_choice_still_wins(self, db):
        course, staff, room, unit = self._setup(db)
        other = Staff(timetable_session_id=SID, name="B. Nakamura", fte=1.0)
        db.add(other)
        db.flush()
        db.add(
            Booking(
                week_id=1, course_id=course.id, unit_id=unit.id, staff_id=staff.id,
                room_id=room.id, day=0, start_slot=2, end_slot=6, session_part=1,
            )
        )
        db.commit()

        create_booking(
            db,
            timetable_session_id=SID,
            course_id=course.id,
            unit_id=unit.id,
            staff_id=other.id,
            room_id=None,
            day=1,
            start_slot=2,
            end_slot=4,
        )

        part2 = db.query(Booking).filter(Booking.session_part == 2).one()
        # Inheriting is a default, not an override.
        assert part2.staff_id == other.id
        assert part2.room_id == room.id


class TestRepeatOneRequest:
    def _request(self, db, *, day: dt.date, booking_id: int = 11) -> CoverRequest:
        r = CoverRequest(
            timetable_session_id=SID,
            booking_id=booking_id,
            cover_date=day,
            week_number=3,
            unit_name="Design and implement a server solution",
            away_staff_name="A. Rivers",
            cover_staff_name="B. Nakamura",
        )
        db.add(r)
        db.commit()
        return r

    def test_copies_that_one_request_a_week_on(self, db):
        r = self._request(db, day=dt.date(2026, 3, 2))

        out = duplicate_request_next_week(db, timetable_session_id=SID, request_id=r.id)

        assert out["created"] == 1
        rows = db.query(CoverRequest).order_by(CoverRequest.cover_date).all()
        assert [x.cover_date for x in rows] == [dt.date(2026, 3, 2), dt.date(2026, 3, 9)]
        copy = rows[1]
        assert copy.cover_staff_name == "B. Nakamura"
        assert copy.week_number == 4

    def test_leaves_every_other_request_alone(self, db):
        first = self._request(db, day=dt.date(2026, 3, 2), booking_id=11)
        self._request(db, day=dt.date(2026, 3, 2), booking_id=12)

        duplicate_request_next_week(db, timetable_session_id=SID, request_id=first.id)

        # Three rows, not four: the other class was not dragged along.
        assert db.query(CoverRequest).count() == 3
        assert db.query(CoverRequest).filter(CoverRequest.booking_id == 12).count() == 1

    def test_pressing_twice_does_not_stack_duplicates(self, db):
        r = self._request(db, day=dt.date(2026, 3, 2))

        duplicate_request_next_week(db, timetable_session_id=SID, request_id=r.id)
        again = duplicate_request_next_week(db, timetable_session_id=SID, request_id=r.id)

        assert again["created"] == 0
        assert db.query(CoverRequest).count() == 2

    def test_walking_the_copy_forward_extends_the_run(self, db):
        r = self._request(db, day=dt.date(2026, 3, 2))
        first = duplicate_request_next_week(db, timetable_session_id=SID, request_id=r.id)
        duplicate_request_next_week(db, timetable_session_id=SID, request_id=first["id"])

        assert [x.cover_date for x in db.query(CoverRequest).order_by(CoverRequest.cover_date)] == [
            dt.date(2026, 3, 2),
            dt.date(2026, 3, 9),
            dt.date(2026, 3, 16),
        ]

    def test_a_request_with_no_date_is_refused(self, db):
        r = CoverRequest(timetable_session_id=SID, booking_id=11, cover_date=None)
        db.add(r)
        db.commit()

        with pytest.raises(ValueError, match="no date"):
            duplicate_request_next_week(db, timetable_session_id=SID, request_id=r.id)

    def test_a_request_from_another_session_is_not_found(self, db):
        r = self._request(db, day=dt.date(2026, 3, 2))

        with pytest.raises(LookupError):
            duplicate_request_next_week(db, timetable_session_id=999, request_id=r.id)

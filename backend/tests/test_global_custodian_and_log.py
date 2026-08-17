"""Workspace-level custodian pinning, and the cover log's running shortfall.

Both features exist because a workspace is the level a department actually
works at: one class has one owner across campuses, and one lecturer's debt
comes down job by job wherever the jobs were logged.
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

from timetable.core.models import (  # noqa: E402
    Base,
    Booking,
    Course,
    Semester,
    Staff,
    Unit,
    Week,
)
from timetable.core.tenancy_models import (  # noqa: E402
    CoverLogEntry,
    GlobalSession,
    GlobalSessionMember,
    Organization,
    TimetableSession,
)

from app.services.class_custodians import class_custodians_for_session  # noqa: E402
from app.services.cover_log import list_cover_log_entries  # noqa: E402
from app.services.global_sessions import (  # noqa: E402
    aggregated_class_custodians,
    set_global_class_custodian,
)

CLASS = "Network Security Fundamentals — VU23217"


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


class World:
    """Two sessions in one workspace, both teaching the same class."""

    def __init__(self, db, *, second_has_williams: bool = True):
        self.db = db
        org = Organization(name="T", slug="t")
        db.add(org)
        db.flush()
        self.group = GlobalSession(organization_id=org.id, name="Dept")
        db.add(self.group)
        db.flush()

        self.sessions: list[TimetableSession] = []
        self.units: dict[int, Unit] = {}
        for index, label in enumerate(("Campus 1", "Campus 2")):
            ts = TimetableSession(organization_id=org.id, name=label)
            db.add(ts)
            db.flush()
            db.add(
                GlobalSessionMember(global_session_id=self.group.id, timetable_session_id=ts.id)
            )
            sem = Semester(timetable_session_id=ts.id, name="S1", num_weeks=18)
            db.add(sem)
            db.flush()
            week = Week(semester_id=sem.id, week_number=0, label="Repeating")
            db.add(week)
            db.flush()
            course = Course(timetable_session_id=ts.id, code=f"G{index}")
            unit = Unit(timetable_session_id=ts.id, name=CLASS, length_slots=4)
            db.add_all([course, unit])
            db.flush()

            names = ["Serena Williams", "Nelson Mandela"]
            if index == 1 and not second_has_williams:
                names = ["Nelson Mandela"]
            staff = [Staff(timetable_session_id=ts.id, name=n) for n in names]
            db.add_all(staff)
            db.flush()
            # A delivery each, so the class has a derived custodian to override.
            db.add(
                Booking(
                    course_id=course.id,
                    unit_id=unit.id,
                    staff_id=staff[0].id,
                    week_id=week.id,
                    day=0,
                    start_slot=4,
                    end_slot=8,
                )
            )
            self.sessions.append(ts)
            self.units[ts.id] = unit
        db.commit()

    def custodian_row(self, ts: TimetableSession) -> dict:
        report = class_custodians_for_session(self.db, timetable_session_id=ts.id)
        return next(r for r in report["rows"] if r["unit_name"] == CLASS)

    def pinned_ids(self) -> list[int | None]:
        return [self.units[ts.id].custodian_staff_id for ts in self.sessions]


class TestGlobalCustodianPin:
    def test_pin_writes_through_to_every_session(self, db):
        w = World(db)

        result = set_global_class_custodian(
            db, global_session_id=w.group.id, unit_name=CLASS, staff_name="Nelson Mandela"
        )

        assert result["applied"] == 2
        assert not result["skipped_sessions"]
        for ts in w.sessions:
            row = w.custodian_row(ts)
            assert row["custodian"].startswith("Nelson Mandela")
            assert row["custodian_is_manual"] is True

    def test_unpin_clears_every_session(self, db):
        w = World(db)
        set_global_class_custodian(
            db, global_session_id=w.group.id, unit_name=CLASS, staff_name="Nelson Mandela"
        )

        set_global_class_custodian(
            db, global_session_id=w.group.id, unit_name=CLASS, staff_name=None
        )

        assert w.pinned_ids() == [None, None]
        for ts in w.sessions:
            assert w.custodian_row(ts)["custodian_is_manual"] is False

    def test_session_without_that_lecturer_is_skipped_and_named(self, db):
        w = World(db, second_has_williams=False)

        result = set_global_class_custodian(
            db, global_session_id=w.group.id, unit_name=CLASS, staff_name="Serena Williams"
        )

        # Campus 1 gets the pin; campus 2 has no Williams, so it is reported.
        assert result["applied"] == 1
        assert result["skipped_sessions"] == ["Campus 2"]
        assert w.pinned_ids()[1] is None

    def test_aggregated_row_marks_the_pin_and_offers_choices(self, db):
        w = World(db)

        rows = aggregated_class_custodians(db, w.group.id)["rows"]
        row = next(r for r in rows if r["unit_name"] == CLASS)
        # Before any pin: whoever teaches it. Mandela teaches nothing here.
        assert row["custodian_choices"] == ["Serena Williams"]
        assert row["custodian_is_manual"] is False

        set_global_class_custodian(
            db, global_session_id=w.group.id, unit_name=CLASS, staff_name="Nelson Mandela"
        )
        rows = aggregated_class_custodians(db, w.group.id)["rows"]
        row = next(r for r in rows if r["unit_name"] == CLASS)

        assert row["custodian_is_manual"] is True
        # A custodian pinned from outside the teaching list still has to appear
        # in the dropdown that shows him as the current value.
        assert row["custodian_choices"] == ["Nelson Mandela", "Serena Williams"]

    def test_unknown_class_name_applies_nothing(self, db):
        w = World(db)

        result = set_global_class_custodian(
            db, global_session_id=w.group.id, unit_name="No Such Class", staff_name="Nelson Mandela"
        )

        assert result["applied"] == 0
        assert w.pinned_ids() == [None, None]


class TestCoverLogShortfall:
    def _log(self, db, gsid: int, name: str, day: int, hours: float) -> CoverLogEntry:
        entry = CoverLogEntry(
            global_session_id=gsid,
            cover_date=_dt.date(2026, 8, day),
            day_label="Monday",
            time_label="09:00 – 11:00",
            group_name="G0",
            unit_name=CLASS,
            room_code="A1",
            away_staff_name="Cathy Freeman",
            cover_staff_name=name,
            hours=hours,
        )
        db.add(entry)
        db.commit()
        return entry

    def test_debt_comes_down_entry_by_entry(self, db, monkeypatch):
        w = World(db)
        # owed = |variance| x 20 semester weeks, so -0.3/week is 6 hours owed;
        # the two entries below cover 3 of them.
        monkeypatch.setattr(
            "app.services.global_sessions.aggregated_staff",
            lambda _db, _gsid: [{"name": "Nelson Mandela", "variance": -0.3}],
        )
        self._log(db, w.group.id, "Nelson Mandela", 3, 2.0)
        self._log(db, w.group.id, "Nelson Mandela", 10, 1.0)

        rows = list_cover_log_entries(db, global_session_id=w.group.id)

        # Newest first: the later job starts from what the earlier one left.
        assert [r["cover_date"] for r in rows] == ["2026-08-10", "2026-08-03"]
        assert rows[1]["hours_owed_before"] == 6.0
        assert rows[1]["hours_owed_after"] == 4.0
        assert rows[0]["hours_owed_before"] == 4.0
        assert rows[0]["hours_owed_after"] == 3.0

    def test_lecturer_not_behind_shows_nothing(self, db, monkeypatch):
        w = World(db)
        monkeypatch.setattr(
            "app.services.global_sessions.aggregated_staff",
            lambda _db, _gsid: [{"name": "Nelson Mandela", "variance": 2.0}],
        )
        self._log(db, w.group.id, "Nelson Mandela", 3, 2.0)

        row = list_cover_log_entries(db, global_session_id=w.group.id)[0]

        assert row["hours_owed_before"] is None
        assert row["hours_owed_after"] is None

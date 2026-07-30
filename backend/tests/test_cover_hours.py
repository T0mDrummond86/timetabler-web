"""The cover hours ledger: how long a job was, and what a lecturer still owes.

The arithmetic is pure, so most of this tests ``timetable.core.cover_hours``
directly. The two cases that need a database — that cover accrues only to the
lecturer who covered, and that a session outside any workspace yields no
markings — go through the services.
"""
from __future__ import annotations

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

from timetable.core.cover_hours import (  # noqa: E402
    SEMESTER_WEEKS_FOR_OWED_HOURS,
    hours_from_slots,
    hours_from_time_label,
    hours_owed_for_variance,
    still_to_make_up,
)
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from timetable.core.models import Base, Staff  # noqa: E402
from timetable.core.tenancy_models import (  # noqa: E402
    CoverLogEntry,
    GlobalSession,
    Organization,
    TimetableSession,
)


@pytest.fixture()
def db():
    """A bare database — these cases exercise the services, not the API."""
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


class TestHoursFromSlots:
    def test_span_is_half_an_hour_per_slot(self):
        # 08:00 + 4 slots = 10:00, running to slot 10 = 13:00.
        assert hours_from_slots(4, 10) == 3.0

    def test_single_slot_is_half_an_hour(self):
        assert hours_from_slots(0, 1) == 0.5

    @pytest.mark.parametrize("start,end", [(None, 5), (5, None), (None, None)])
    def test_missing_endpoint_is_unknown(self, start, end):
        assert hours_from_slots(start, end) is None

    @pytest.mark.parametrize("start,end", [(10, 10), (10, 4)])
    def test_empty_or_reversed_span_is_unknown(self, start, end):
        assert hours_from_slots(start, end) is None


class TestHoursFromTimeLabel:
    """Rows logged before hours were recorded are backfilled from their label."""

    @pytest.mark.parametrize(
        "label",
        [
            "09:00 – 12:00",  # en dash
            "09:00 - 12:00",  # hyphen
            "09:00 — 12:00",  # em dash
            "9:00-12:00",  # no padding, single-digit hour
            "09.00 to 12.00",  # dots and a word
            "08.30 — 11.30",  # dotted, half past
        ],
    )
    def test_three_hour_labels_all_read_as_three(self, label):
        assert hours_from_time_label(label) == 3.0

    @pytest.mark.parametrize("label", ["TBC", "not a time", "", None, "09:00"])
    def test_unreadable_label_is_none(self, label):
        # None means "unknown", which the aggregation counts as zero rather
        # than treating as an error.
        assert hours_from_time_label(label) is None

    def test_reversed_label_is_none(self):
        assert hours_from_time_label("12:00 – 09:00") is None

    def test_out_of_range_clock_is_none(self):
        assert hours_from_time_label("09:00 – 34:00") is None


class TestHoursOwed:
    def test_owed_is_shortfall_times_the_semester(self):
        assert hours_owed_for_variance(-3.0) == 3.0 * SEMESTER_WEEKS_FOR_OWED_HOURS
        assert hours_owed_for_variance(-1.2) == 24.0

    @pytest.mark.parametrize("variance", [0.0, 2.0, None])
    def test_on_or_over_target_is_not_tracked(self, variance):
        # Over-hours lecturers are paid out, not tracked here.
        assert hours_owed_for_variance(variance) is None


class TestStillToMakeUp:
    def test_cover_pays_down_the_debt(self):
        assert still_to_make_up(60.0, 12.0) == 48.0

    def test_covering_more_than_owed_lands_on_zero(self):
        # Square, not in credit.
        assert still_to_make_up(60.0, 80.0) == 0.0

    def test_no_cover_leaves_the_full_debt(self):
        assert still_to_make_up(60.0, 0.0) == 60.0

    def test_untracked_lecturer_stays_untracked(self):
        assert still_to_make_up(None, 12.0) is None


class TestLedgerFor:
    """The three figures as the staff tab receives them."""

    def test_zero_cover_reads_as_zero_not_blank(self):
        from app.services.cover_ledger import ledger_for

        assert ledger_for(-1.0, 0.0) == {
            "hours_owed": 20.0,
            "cover_hours_done": 0.0,
            "still_to_make_up": 20.0,
        }

    def test_over_target_leaves_every_figure_empty(self):
        from app.services.cover_ledger import ledger_for

        assert ledger_for(2.0, 5.0) == {
            "hours_owed": None,
            "cover_hours_done": None,
            "still_to_make_up": None,
        }

    def test_varies_has_no_single_shortfall_to_report(self):
        from app.services.cover_ledger import ledger_for

        # Amalgamated staff yield the string "Varies" when sessions disagree.
        assert ledger_for("Varies", 5.0)["hours_owed"] is None


class TestAccrual:
    """Who a logged cover job is credited to."""

    def _workspace(self, db, name: str = "Workspace"):
        """A global workspace. Repeat calls share one org (the slug is unique)
        and need distinct names (name is unique within an org)."""
        org = db.query(Organization).first()
        if org is None:
            org = Organization(name="Test", slug="test")
            db.add(org)
            db.flush()
        gs = GlobalSession(organization_id=org.id, name=name)
        db.add(gs)
        db.flush()
        return gs

    def _log(self, db, gs, *, cover: str, away: str, hours: float | None):
        import datetime as dt

        db.add(
            CoverLogEntry(
                global_session_id=gs.id,
                cover_date=dt.date(2026, 7, 30),
                time_label="09:00 - 12:00",
                cover_staff_name=cover,
                away_staff_name=away,
                hours=hours,
            )
        )
        db.commit()

    def test_only_the_cover_lecturer_is_credited(self, db):
        from app.services.cover_ledger import cover_hours_by_lecturer

        gs = self._workspace(db)
        self._log(db, gs, cover="Dana Reyes", away="Sam Patel", hours=3.0)

        totals = cover_hours_by_lecturer(db, gs.id)
        assert totals["dana reyes"] == 3.0
        # Being covered is not a debit — the away lecturer is untouched.
        assert "sam patel" not in totals

    def test_jobs_accumulate_across_the_workspace(self, db):
        from app.services.cover_ledger import cover_hours_by_lecturer

        gs = self._workspace(db)
        self._log(db, gs, cover="Dana Reyes", away="Sam Patel", hours=3.0)
        self._log(db, gs, cover="Dana Reyes", away="Kim Lee", hours=1.5)

        assert cover_hours_by_lecturer(db, gs.id)["dana reyes"] == 4.5

    def test_unreadable_hours_count_as_zero_not_as_an_error(self, db):
        from app.services.cover_ledger import cover_hours_by_lecturer

        gs = self._workspace(db)
        self._log(db, gs, cover="Dana Reyes", away="Sam Patel", hours=None)
        self._log(db, gs, cover="Dana Reyes", away="Kim Lee", hours=2.0)

        assert cover_hours_by_lecturer(db, gs.id)["dana reyes"] == 2.0

    def test_names_match_however_they_were_typed(self, db):
        from app.services.cover_ledger import cover_hours_by_lecturer

        gs = self._workspace(db)
        self._log(db, gs, cover="Dana Reyes", away="Sam Patel", hours=3.0)
        self._log(db, gs, cover="  dana REYES ", away="Kim Lee", hours=1.0)

        # Same lecturer, two spellings — one ledger line.
        assert cover_hours_by_lecturer(db, gs.id) == {"dana reyes": 4.0}

    def test_another_workspace_does_not_leak_in(self, db):
        from app.services.cover_ledger import cover_hours_by_lecturer

        mine = self._workspace(db, "Mine")
        theirs = self._workspace(db, "Theirs")
        self._log(db, theirs, cover="Dana Reyes", away="Sam Patel", hours=3.0)

        assert cover_hours_by_lecturer(db, mine.id) == {}


class TestCandidateMarking:
    def test_session_outside_any_workspace_marks_nobody(self, db):
        from app.services.cover_lecturers import _shortfall_by_lecturer

        org = Organization(name="Test", slug="test")
        db.add(org)
        db.flush()
        session = TimetableSession(organization_id=org.id, name="Standalone")
        db.add(session)
        db.flush()
        db.add(Staff(name="Dana Reyes", timetable_session_id=session.id, fte=1.0))
        db.commit()

        # No workspace means no cover log and no ledger, so nobody is marked
        # rather than the picker failing.
        assert _shortfall_by_lecturer(db, session.id) == {}

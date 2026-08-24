"""The "Hours owed" / "Owed after cover" columns on the session Staff tab.

The figure has to match what the Lecturer cover panel shows for the same
person, and the only way it can is by using the workspace-aggregated variance
rather than the session's own. A lecturer teaching across two linked timetables
is short against their combined load, not against either half, so the
two-session case below is the one that actually pins the behaviour down.
"""
from __future__ import annotations

import os
from datetime import date
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

from timetable.core.models import Base, Staff  # noqa: E402
from timetable.core.cover_hours import SEMESTER_WEEKS_FOR_OWED_HOURS  # noqa: E402
from timetable.core.tenancy_models import (  # noqa: E402
    CoverLogEntry,
    GlobalSession,
    GlobalSessionMember,
    Organization,
    TimetableSession,
)

from app.services.staff_hours_table import staff_hours_table_rows  # noqa: E402

ORG = 1


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    org = Organization(id=ORG, name="T", slug="t")
    session.add(org)
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _session(db, sid: int, name: str) -> TimetableSession:
    row = TimetableSession(id=sid, organization_id=ORG, name=name)
    db.add(row)
    db.flush()
    return row


def _workspace(db, gsid: int, *session_ids: int) -> GlobalSession:
    gs = GlobalSession(id=gsid, organization_id=ORG, name="WS")
    db.add(gs)
    db.flush()
    for sid in session_ids:
        db.add(GlobalSessionMember(global_session_id=gsid, timetable_session_id=sid))
    db.flush()
    return gs


def _staff(db, sid: int, name: str, *, fte: float, supervision: float = 0.0) -> Staff:
    """A lecturer whose only non-teaching load is supervision.

    Total hours come out as `supervision`, so variance is
    `supervision - fte * 21` and each test can state the shortfall it wants
    without having to schedule any bookings.
    """
    s = Staff(timetable_session_id=sid, name=name, fte=fte, supervision_hours=supervision)
    db.add(s)
    db.flush()
    return s


def _cover(db, gsid: int, name: str, hours: float) -> None:
    """A logged cover job. cover_date is NOT NULL, and is not read by the
    ledger -- only the covering lecturer and the hours matter."""
    db.add(
        CoverLogEntry(
            global_session_id=gsid,
            cover_date=date(2026, 3, 2),
            cover_staff_name=name,
            hours=hours,
        )
    )


def _row(db, sid: int, name: str) -> dict:
    rows = staff_hours_table_rows(db, timetable_session_id=sid)
    return next(r for r in rows if r["name"] == name)


class TestSingleSession:
    def test_under_hours_owes_the_shortfall_across_the_semester(self, db):
        _session(db, 1, "Joondalup")
        _workspace(db, 10, 1)
        # 0.5 FTE -> 10.5 lecturing hours; 8.5 carried -> 2.0 short each week.
        _staff(db, 1, "A. Rivers", fte=0.5, supervision=8.5)
        db.commit()

        row = _row(db, 1, "A. Rivers")

        assert row["variance"] == pytest.approx(-2.0)
        assert row["hours_owed"] == pytest.approx(2.0 * SEMESTER_WEEKS_FOR_OWED_HOURS)
        # Nothing covered yet, so the whole debt is still outstanding.
        assert row["hours_owed_after_cover"] == pytest.approx(row["hours_owed"])

    def test_on_or_over_target_leaves_both_blank(self, db):
        _session(db, 1, "Joondalup")
        _workspace(db, 10, 1)
        _staff(db, 1, "Over", fte=0.5, supervision=14.0)  # +3.5
        _staff(db, 1, "Exactly", fte=0.5, supervision=10.5)  # 0.0
        db.commit()

        for name in ("Over", "Exactly"):
            row = _row(db, 1, name)
            assert row["hours_owed"] is None, name
            assert row["hours_owed_after_cover"] is None, name


class TestAcrossLinkedSessions:
    """The case the whole design hangs on.

    aggregated_staff combines *teaching* load across linked sessions, but takes
    each lecturer's non-teaching allowances from that session's own Staff row.
    When those rows disagree it reports the variance as "Varies" rather than
    picking one, and the ledger is then blank by design.
    """

    def test_one_combined_figure_when_the_sessions_agree(self, db):
        _session(db, 1, "Joondalup")
        _session(db, 2, "Northbridge")
        _workspace(db, 10, 1, 2)
        # 21 lecturing hours expected, 15 carried -> 6.0 short.
        _staff(db, 1, "A. Rivers", fte=1.0, supervision=15.0)
        _staff(db, 2, "A. Rivers", fte=1.0, supervision=15.0)
        db.commit()

        row = _row(db, 1, "A. Rivers")

        assert row["hours_owed"] == pytest.approx(6.0 * SEMESTER_WEEKS_FOR_OWED_HOURS)
        assert row["hours_owed_after_cover"] == pytest.approx(row["hours_owed"])

    def test_blank_rather_than_the_local_figure_when_sessions_disagree(self, db):
        _session(db, 1, "Joondalup")
        _session(db, 2, "Northbridge")
        _workspace(db, 10, 1, 2)
        # The same lecturer with different allowances recorded in each session.
        _staff(db, 1, "B. Nakamura", fte=1.0, supervision=6.0)
        _staff(db, 2, "B. Nakamura", fte=1.0, supervision=9.0)
        db.commit()

        row = _row(db, 1, "B. Nakamura")

        # Taken locally she looks 15 hours a week short, which would read as a
        # 300-hour debt. The workspace cannot agree a single variance, so the
        # column stays empty instead of publishing a number the cover panel
        # would contradict. Fixing the disagreement is a data question, not
        # something this column should paper over.
        assert row["variance"] == pytest.approx(-15.0)
        assert row["hours_owed"] is None
        assert row["hours_owed_after_cover"] is None


class TestCoverIsCredited:
    def _under_by(self, db, hours: float) -> None:
        _session(db, 1, "Joondalup")
        _workspace(db, 10, 1)
        _staff(db, 1, "C. Okonkwo", fte=0.5, supervision=10.5 - hours)

    def test_logged_cover_reduces_what_is_still_owed(self, db):
        self._under_by(db, 2.0)
        _cover(db, 10, "C. Okonkwo", 12.0)
        db.commit()

        row = _row(db, 1, "C. Okonkwo")

        assert row["hours_owed"] == pytest.approx(40.0)
        assert row["hours_owed_after_cover"] == pytest.approx(28.0)

    def test_covering_more_than_owed_settles_at_zero_not_negative(self, db):
        self._under_by(db, 1.0)  # owes 20
        _cover(db, 10, "C. Okonkwo", 50.0)
        db.commit()

        row = _row(db, 1, "C. Okonkwo")

        assert row["hours_owed"] == pytest.approx(20.0)
        # Square, not in credit.
        assert row["hours_owed_after_cover"] == pytest.approx(0.0)

    def test_cover_is_matched_regardless_of_name_casing(self, db):
        self._under_by(db, 2.0)
        _cover(db, 10, "  c. OKONKWO ", 10.0)
        db.commit()

        assert _row(db, 1, "C. Okonkwo")["hours_owed_after_cover"] == pytest.approx(30.0)


class TestWithoutAWorkspace:
    def test_falls_back_to_the_local_variance_with_nothing_covered(self, db):
        # No GlobalSessionMember row: there is no cover log to read.
        _session(db, 1, "Standalone")
        _staff(db, 1, "D. Solo", fte=0.5, supervision=8.5)
        db.commit()

        row = _row(db, 1, "D. Solo")

        assert row["hours_owed"] == pytest.approx(40.0)
        # No cover log means nothing has been paid back, so the two agree.
        assert row["hours_owed_after_cover"] == pytest.approx(40.0)

    def test_still_blank_when_not_under_hours(self, db):
        _session(db, 1, "Standalone")
        _staff(db, 1, "E. Fine", fte=0.5, supervision=12.0)
        db.commit()

        row = _row(db, 1, "E. Fine")

        assert row["hours_owed"] is None
        assert row["hours_owed_after_cover"] is None

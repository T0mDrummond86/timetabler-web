"""Splitting a qualification into per-stage qualifications.

The split rewrites structure — new qualification rows, renamed group courses,
re-linked classes — so these lock the parts that would be painful to get wrong:
that nothing is silently dropped, that a timetabled qualification is refused,
and that links to *other* qualifications are left alone.
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

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from timetable.core.models import (  # noqa: E402
    Base,
    Booking,
    Course,
    Qualification,
    Semester,
    Unit,
    UnitQualification,
    Week,
)
from timetable.core.tenancy_models import Organization, TimetableSession  # noqa: E402

from app.services.qualification_stages import (  # noqa: E402
    StagePlan,
    StageSplitError,
    split_qualification_into_stages,
    stage_split_preview,
)

SID = 1


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


def _qual(db, name: str, groups: int = 1) -> Qualification:
    q = Qualification(timetable_session_id=SID, name=name, num_groups=groups)
    db.add(q)
    db.flush()
    return q


def _unit(db, name: str, *quals: Qualification) -> Unit:
    u = Unit(timetable_session_id=SID, name=name)
    db.add(u)
    db.flush()
    for q in quals:
        db.add(UnitQualification(unit_id=u.id, qualification_id=q.id))
    db.flush()
    return u


def _split(db, qual, stages):
    return split_qualification_into_stages(
        db, timetable_session_id=SID, qualification_id=qual.id, stages=stages
    )


def _classes_of(db, qual_id: int) -> set[str]:
    return {
        u.name
        for u in db.query(Unit)
        .join(UnitQualification, UnitQualification.unit_id == Unit.id)
        .filter(UnitQualification.qualification_id == qual_id)
        .all()
    }


class TestSplit:
    def test_deals_classes_into_one_qualification_per_stage(self, db):
        q = _qual(db, "Dip", groups=2)
        a, b, c = _unit(db, "A", q), _unit(db, "B", q), _unit(db, "C", q)
        db.commit()

        out = _split(db, q, [
            StagePlan("Dip Stg1", 2, (a.id,)),
            StagePlan("Dip Stg2", 1, (b.id, c.id)),
        ])

        ids = out["stage_qualification_ids"]
        assert len(ids) == 2
        # The original record becomes stage one, so its id survives.
        assert ids[0] == q.id
        assert _classes_of(db, ids[0]) == {"A"}
        assert _classes_of(db, ids[1]) == {"B", "C"}

    def test_each_stage_gets_its_own_group_courses(self, db):
        q = _qual(db, "Dip", groups=1)
        a, b = _unit(db, "A", q), _unit(db, "B", q)
        db.commit()

        out = _split(db, q, [
            StagePlan("Dip Stg1", 1, (a.id,)),
            StagePlan("Dip Stg2", 3, (b.id,)),
        ])

        first, second = out["stage_qualification_ids"]
        assert db.query(Course).filter_by(qualification_id=first).count() == 1
        assert db.query(Course).filter_by(qualification_id=second).count() == 3
        # Courses are named from their own stage, not the pre-split name.
        codes = {c.code for c in db.query(Course).filter_by(qualification_id=second).all()}
        assert all(code.startswith("Dip Stg2") for code in codes), codes

    def test_unassigned_classes_stay_on_the_first_stage(self, db):
        q = _qual(db, "Dip")
        a, orphan = _unit(db, "A", q), _unit(db, "Orphan", q)
        db.commit()

        out = _split(db, q, [
            StagePlan("Dip Stg1", 1, (a.id,)),
            StagePlan("Dip Stg2", 1, ()),
        ])

        assert out["unassigned_classes_kept_on_first_stage"] == 1
        assert "Orphan" in _classes_of(db, out["stage_qualification_ids"][0])

    def test_links_to_other_qualifications_are_untouched(self, db):
        q = _qual(db, "Dip")
        other = _qual(db, "Elsewhere")
        shared = _unit(db, "Shared", q, other)
        db.commit()

        out = _split(db, q, [
            StagePlan("Dip Stg1", 1, ()),
            StagePlan("Dip Stg2", 1, (shared.id,)),
        ])

        assert _classes_of(db, out["stage_qualification_ids"][1]) == {"Shared"}
        # A class can belong to several qualifications; the split is not
        # licence to unpick the ones it was not asked about.
        assert _classes_of(db, other.id) == {"Shared"}


class TestRefusals:
    def _with_booking(self, db) -> Qualification:
        q = _qual(db, "Dip")
        _unit(db, "A", q)
        course = Course(code="Dip GrpA", qualification_id=q.id, timetable_session_id=SID)
        sem = Semester(timetable_session_id=SID, name="S1")
        db.add_all([course, sem])
        db.flush()
        week = Week(semester_id=sem.id, week_number=0)
        db.add(week)
        db.flush()
        db.add(Booking(week_id=week.id, course_id=course.id, day=0, start_slot=0, end_slot=2))
        db.commit()
        return q

    def test_refuses_when_the_qualification_is_already_timetabled(self, db):
        q = self._with_booking(db)
        with pytest.raises(StageSplitError, match="scheduled"):
            _split(db, q, [StagePlan("Dip Stg1", 1, ()), StagePlan("Dip Stg2", 1, ())])

    def test_preview_reports_the_block_rather_than_failing(self, db):
        q = self._with_booking(db)
        out = stage_split_preview(db, timetable_session_id=SID, qualification_id=q.id)
        assert out["can_split"] is False
        assert "scheduled" in out["blocked_reason"]

    def test_refuses_a_class_in_two_stages(self, db):
        q = _qual(db, "Dip")
        a = _unit(db, "A", q)
        db.commit()
        with pytest.raises(StageSplitError, match="one stage"):
            _split(db, q, [StagePlan("S1", 1, (a.id,)), StagePlan("S2", 1, (a.id,))])

    def test_refuses_a_class_from_another_qualification(self, db):
        q = _qual(db, "Dip")
        other = _qual(db, "Elsewhere")
        stranger = _unit(db, "Stranger", other)
        db.commit()
        with pytest.raises(StageSplitError, match="already linked"):
            _split(db, q, [StagePlan("S1", 1, (stranger.id,)), StagePlan("S2", 1, ())])

    def test_refuses_a_name_that_already_exists(self, db):
        q = _qual(db, "Dip")
        _qual(db, "Taken")
        db.commit()
        with pytest.raises(StageSplitError, match="already exists"):
            _split(db, q, [StagePlan("Taken", 1, ()), StagePlan("Dip Stg2", 1, ())])

    def test_refuses_duplicate_stage_names(self, db):
        q = _qual(db, "Dip")
        db.commit()
        with pytest.raises(StageSplitError, match="differ"):
            _split(db, q, [StagePlan("Same", 1, ()), StagePlan("same", 1, ())])

    def test_refuses_fewer_than_two_stages(self, db):
        q = _qual(db, "Dip")
        db.commit()
        with pytest.raises(StageSplitError, match="at least two"):
            _split(db, q, [StagePlan("Only", 1, ())])

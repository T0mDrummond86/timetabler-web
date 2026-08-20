"""Merging two qualifications into a new third one.

The defining property is that a merge *adds*. Stage split rewrites structure
and can lose things if it is wrong; a merge must not be able to, because both
sources are still in use the moment it finishes. So most of what is asserted
here is what did **not** change: the sources' names, groups, class links and
bookings all have to come through a merge untouched.
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
    QualificationTimeWindow,
    Semester,
    Staff,
    StaffQualificationOnlineStudents,
    Unit,
    UnitQualification,
    Week,
)
from timetable.core.tenancy_models import Organization, TimetableSession  # noqa: E402

from app.services.qualification_merge import (  # noqa: E402
    QualificationMergeError,
    merge_preview,
    merge_qualifications,
    suggested_merge_name,
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


def _qual(db, name: str, groups: int = 1, period: str = "day", mode: str = "regular"):
    q = Qualification(
        timetable_session_id=SID,
        name=name,
        num_groups=groups,
        schedule_period=period,
        delivery_mode=mode,
    )
    db.add(q)
    db.flush()
    return q


def _unit(db, name: str, *quals):
    u = Unit(timetable_session_id=SID, name=name)
    db.add(u)
    db.flush()
    for q in quals:
        db.add(UnitQualification(unit_id=u.id, qualification_id=q.id))
    db.flush()
    return u


def _merge(db, first, second, name="Merged", groups=1, **kw):
    return merge_qualifications(
        db,
        timetable_session_id=SID,
        first_qualification_id=first.id,
        second_qualification_id=second.id,
        name=name,
        num_groups=groups,
        **kw,
    )


def _book(db, course, unit, *, day=0, start=0, end=2):
    """One booking on a cohort, with the semester week it needs to hang off."""
    sem = Semester(timetable_session_id=SID, name="S1")
    db.add(sem)
    db.flush()
    week = Week(semester_id=sem.id, week_number=0)
    db.add(week)
    db.flush()
    booking = Booking(
        week_id=week.id,
        course_id=course.id,
        unit_id=unit.id,
        day=day,
        start_slot=start,
        end_slot=end,
    )
    db.add(booking)
    db.flush()
    return booking


def _classes_of(db, qual_id: int) -> set[str]:
    return {
        u.name
        for u in db.query(Unit)
        .join(UnitQualification, UnitQualification.unit_id == Unit.id)
        .filter(UnitQualification.qualification_id == qual_id)
        .all()
    }


class TestMerge:
    def test_new_qualification_holds_both_class_lists(self, db):
        a, b = _qual(db, "Cert III"), _qual(db, "Cert IV")
        _unit(db, "Networking", a)
        _unit(db, "Databases", a)
        _unit(db, "Security", b)
        db.commit()

        out = _merge(db, a, b, name="Cert III+IV")

        assert _classes_of(db, out["qualification_id"]) == {
            "Networking",
            "Databases",
            "Security",
        }
        assert out["class_count"] == 3

    def test_a_class_in_both_is_linked_once(self, db):
        a, b = _qual(db, "A"), _qual(db, "B")
        shared = _unit(db, "Shared", a, b)
        _unit(db, "OnlyA", a)
        db.commit()

        out = _merge(db, a, b)

        links = (
            db.query(UnitQualification)
            .filter(
                UnitQualification.qualification_id == out["qualification_id"],
                UnitQualification.unit_id == shared.id,
            )
            .count()
        )
        assert links == 1
        assert out["class_count"] == 2
        assert out["shared_class_count"] == 1


class TestSourcesSurvive:
    """The whole point of the design: a merge takes nothing away."""

    def test_both_sources_still_exist_with_their_names(self, db):
        a, b = _qual(db, "Cert III"), _qual(db, "Cert IV")
        _unit(db, "Networking", a)
        _unit(db, "Security", b)
        db.commit()

        _merge(db, a, b, name="Combined")

        names = {
            q.name
            for q in db.query(Qualification)
            .filter(Qualification.timetable_session_id == SID)
            .all()
        }
        assert names == {"Cert III", "Cert IV", "Combined"}

    def test_sources_keep_their_own_class_links(self, db):
        a, b = _qual(db, "A"), _qual(db, "B")
        _unit(db, "OnlyA", a)
        _unit(db, "OnlyB", b)
        db.commit()

        _merge(db, a, b)

        # Unchanged -- the merge linked classes to the new record, it did not
        # move them off these.
        assert _classes_of(db, a.id) == {"OnlyA"}
        assert _classes_of(db, b.id) == {"OnlyB"}

    def test_source_cohorts_and_their_bookings_are_untouched(self, db):
        a, b = _qual(db, "A", groups=2), _qual(db, "B", groups=1)
        unit = _unit(db, "Networking", a)
        course = Course(timetable_session_id=SID, code="A GrpA", qualification_id=a.id)
        db.add(course)
        db.flush()
        _book(db, course, unit, day=0, start=2, end=6)
        db.commit()

        _merge(db, a, b, name="Combined", groups=3)

        # The source's own cohort, and the booking on it, are exactly as before.
        assert db.query(Course).filter(Course.id == course.id).one().qualification_id == a.id
        assert db.query(Booking).filter(Booking.course_id == course.id).count() == 1
        assert db.query(Qualification).filter(Qualification.id == a.id).one().num_groups == 2

    def test_merging_a_timetabled_qualification_is_allowed(self, db):
        """Unlike a stage split, which must refuse -- nothing here can be orphaned."""
        a, b = _qual(db, "A"), _qual(db, "B")
        unit = _unit(db, "Networking", a)
        _unit(db, "Security", b)
        course = Course(timetable_session_id=SID, code="A GrpA", qualification_id=a.id)
        db.add(course)
        db.flush()
        _book(db, course, unit, day=1, start=4, end=6)
        db.commit()

        out = _merge(db, a, b)  # no raise

        assert out["class_count"] == 2


class TestNewQualificationSetup:
    def test_gets_its_own_group_cohorts(self, db):
        a, b = _qual(db, "A"), _qual(db, "B")
        _unit(db, "X", a)
        db.commit()

        out = _merge(db, a, b, name="Combined", groups=3)

        courses = (
            db.query(Course)
            .filter(Course.qualification_id == out["qualification_id"])
            .all()
        )
        assert len(courses) == 3
        assert all(c.code.startswith("Combined") for c in courses)

    def test_gets_time_windows_for_the_chosen_period(self, db):
        a, b = _qual(db, "A", period="day"), _qual(db, "B", period="night")
        _unit(db, "X", a)
        db.commit()

        out = _merge(db, a, b, schedule_period="night")

        merged = db.query(Qualification).filter(
            Qualification.id == out["qualification_id"]
        ).one()
        assert merged.schedule_period == "night"
        assert db.query(QualificationTimeWindow).filter(
            QualificationTimeWindow.qualification_id == merged.id
        ).count() > 0

    def test_period_defaults_to_the_first_qualifications(self, db):
        a, b = _qual(db, "A", period="night"), _qual(db, "B", period="day")
        _unit(db, "X", a)
        db.commit()

        out = _merge(db, a, b)

        assert db.query(Qualification).filter(
            Qualification.id == out["qualification_id"]
        ).one().schedule_period == "night"

    def test_is_never_part_of_a_stage_family(self, db):
        # Merging two stages of one family must not quietly add a third stage
        # to it -- the other stages know nothing about the merged record.
        a = _qual(db, "Dip Stg1")
        a.parent_qualification_id = a.id
        b = _qual(db, "Dip Stg2")
        b.parent_qualification_id = a.id
        _unit(db, "X", a)
        db.commit()

        out = _merge(db, a, b, name="Dip combined")

        assert db.query(Qualification).filter(
            Qualification.id == out["qualification_id"]
        ).one().parent_qualification_id is None

    def test_online_student_counts_are_added_together(self, db):
        a, b = _qual(db, "A"), _qual(db, "B")
        _unit(db, "X", a)
        staff = Staff(timetable_session_id=SID, name="T. Lecturer")
        db.add(staff)
        db.flush()
        db.add(StaffQualificationOnlineStudents(
            staff_id=staff.id, qualification_id=a.id, student_count=12))
        db.add(StaffQualificationOnlineStudents(
            staff_id=staff.id, qualification_id=b.id, student_count=8))
        db.commit()

        out = _merge(db, a, b)

        row = (
            db.query(StaffQualificationOnlineStudents)
            .filter(
                StaffQualificationOnlineStudents.qualification_id
                == out["qualification_id"]
            )
            .one()
        )
        assert row.student_count == 20
        # And the sources keep theirs.
        assert db.query(StaffQualificationOnlineStudents).filter(
            StaffQualificationOnlineStudents.qualification_id == a.id
        ).one().student_count == 12


class TestRefusals:
    def test_a_qualification_cannot_merge_with_itself(self, db):
        a = _qual(db, "A")
        _unit(db, "X", a)
        db.commit()

        with pytest.raises(QualificationMergeError, match="two different"):
            _merge(db, a, a)

    def test_a_blank_name_is_refused(self, db):
        a, b = _qual(db, "A"), _qual(db, "B")
        _unit(db, "X", a)
        db.commit()

        with pytest.raises(QualificationMergeError, match="needs a name"):
            _merge(db, a, b, name="   ")

    def test_a_name_already_in_use_is_refused(self, db):
        a, b = _qual(db, "A"), _qual(db, "B")
        _unit(db, "X", a)
        db.commit()

        # Including a source's own name: both are still here afterwards, so it
        # would collide on the (session, name) unique constraint.
        with pytest.raises(QualificationMergeError, match="already exists"):
            _merge(db, a, b, name="A")

    def test_merging_two_empty_qualifications_is_refused(self, db):
        a, b = _qual(db, "A"), _qual(db, "B")
        db.commit()

        with pytest.raises(QualificationMergeError, match="nothing to merge"):
            _merge(db, a, b)

    def test_a_missing_qualification_is_a_lookup_error(self, db):
        a = _qual(db, "A")
        _unit(db, "X", a)
        db.commit()

        with pytest.raises(LookupError):
            merge_qualifications(
                db,
                timetable_session_id=SID,
                first_qualification_id=a.id,
                second_qualification_id=99999,
                name="Combined",
                num_groups=1,
            )

    def test_too_many_groups_is_refused(self, db):
        a, b = _qual(db, "A"), _qual(db, "B")
        _unit(db, "X", a)
        db.commit()

        with pytest.raises(QualificationMergeError, match="at most"):
            _merge(db, a, b, groups=99)


class TestPreview:
    def test_reports_both_sides_and_the_combined_total(self, db):
        a, b = _qual(db, "Cert III", groups=2), _qual(db, "Cert IV", groups=3)
        _unit(db, "Shared", a, b)
        _unit(db, "OnlyA", a)
        _unit(db, "OnlyB", b)
        db.commit()

        out = merge_preview(
            db,
            timetable_session_id=SID,
            first_qualification_id=a.id,
            second_qualification_id=b.id,
        )

        assert out["first"]["name"] == "Cert III"
        assert out["first"]["class_count"] == 2
        assert out["second"]["class_count"] == 2
        assert out["shared_class_count"] == 1
        assert out["combined_class_count"] == 3
        assert out["suggested_num_groups"] == 3
        assert {c["name"] for c in out["combined_classes"]} == {
            "Shared", "OnlyA", "OnlyB",
        }

    def test_warns_when_the_schedule_periods_differ(self, db):
        a, b = _qual(db, "A", period="day"), _qual(db, "B", period="night")
        _unit(db, "X", a)
        db.commit()

        out = merge_preview(
            db,
            timetable_session_id=SID,
            first_qualification_id=a.id,
            second_qualification_id=b.id,
        )

        assert any("night" in w for w in out["warnings"])

    def test_reports_source_bookings_without_blocking(self, db):
        a, b = _qual(db, "A"), _qual(db, "B")
        unit = _unit(db, "X", a)
        course = Course(timetable_session_id=SID, code="A GrpA", qualification_id=a.id)
        db.add(course)
        db.flush()
        _book(db, course, unit)
        db.commit()

        out = merge_preview(
            db,
            timetable_session_id=SID,
            first_qualification_id=a.id,
            second_qualification_id=b.id,
        )

        assert out["first"]["booking_count"] == 1


def test_suggested_name_joins_both():
    assert suggested_merge_name("BFF7 Stg1", "BFF7 Stg2") == "BFF7 Stg1 + BFF7 Stg2"
    assert suggested_merge_name("  A  ", "B") == "A + B"

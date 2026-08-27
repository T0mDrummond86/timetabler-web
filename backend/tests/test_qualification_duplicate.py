"""Copying a qualification without copying its classes.

The whole value of this is the thing it does *not* do: it must not create new
Class records. If it ever does, the duplicate's "ICTNWK540" and the original's
become two different classes, and the pair has to be folded back together in
the Classes tab -- which is the manual work this exists to avoid. Most of what
is asserted below is that the class rows are shared, and that the source is
left exactly as it was.
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
    CourseUnit,
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

from app.services.qualification_duplicate import (  # noqa: E402
    QualificationDuplicateError,
    duplicate_preview,
    duplicate_qualification,
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
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    s.add(Organization(id=1, name="T", slug="t"))
    s.flush()
    s.add(TimetableSession(id=SID, organization_id=1, name="S"))
    s.flush()
    sem = Semester(timetable_session_id=SID, name="S1")
    s.add(sem)
    s.flush()
    s.add(Week(id=1, semester_id=sem.id, week_number=0))
    s.commit()
    try:
        yield s
    finally:
        s.close()


def _qual(db, name: str, *, groups: int = 1, period: str = "day", classes: int = 0):
    """A qualification with `groups` cohorts, each holding every class."""
    q = Qualification(
        timetable_session_id=SID, name=name, num_groups=groups, schedule_period=period
    )
    db.add(q)
    db.flush()

    units = []
    for i in range(classes):
        u = Unit(timetable_session_id=SID, name=f"{name} class {i}", length_slots=4)
        db.add(u)
        db.flush()
        db.add(UnitQualification(unit_id=u.id, qualification_id=q.id))
        units.append(u)

    for g in range(groups):
        c = Course(timetable_session_id=SID, code=f"{name} Grp{chr(65 + g)}", qualification_id=q.id)
        db.add(c)
        db.flush()
        for u in units:
            db.add(CourseUnit(course_id=c.id, unit_id=u.id))
    db.commit()
    return q, units


def _dup(db, qual, name=None) -> dict:
    return duplicate_qualification(
        db, timetable_session_id=SID, qualification_id=qual.id, name=name
    )


class TestClassesAreSharedNotCopied:
    def test_no_new_class_records_are_made(self, db):
        source, units = _qual(db, "Cert IV Cyber", classes=3)

        _dup(db, source, name="Cert IV Cyber 2027")

        # The one assertion this whole feature exists for.
        assert db.query(Unit).count() == 3
        assert {u.id for u in db.query(Unit).all()} == {u.id for u in units}

    def test_the_copy_links_the_same_class_rows(self, db):
        source, units = _qual(db, "Cert IV Cyber", classes=3)

        out = _dup(db, source, name="Copy")

        linked = {
            uq.unit_id
            for uq in db.query(UnitQualification).filter(
                UnitQualification.qualification_id == out["qualification_id"]
            )
        }
        assert linked == {u.id for u in units}
        assert out["class_count"] == 3

    def test_editing_a_shared_class_shows_in_both(self, db):
        source, units = _qual(db, "Cert IV Cyber", classes=1)
        out = _dup(db, source, name="Copy")

        units[0].length_slots = 10
        db.commit()

        # Same row, so there is nothing to keep in step -- but if the
        # implementation ever starts copying, this is what breaks.
        linked = (
            db.query(UnitQualification)
            .filter(UnitQualification.qualification_id == out["qualification_id"])
            .one()
        )
        assert db.get(Unit, linked.unit_id).length_slots == 10

    def test_a_qualification_with_no_classes_still_copies(self, db):
        source, _ = _qual(db, "Empty", classes=0)

        out = _dup(db, source, name="Empty copy")

        assert out["class_count"] == 0
        assert db.get(Qualification, out["qualification_id"]) is not None


class TestTheSourceIsUntouched:
    def test_its_classes_groups_and_settings_are_unchanged(self, db):
        source, units = _qual(db, "Cert IV Cyber", groups=2, classes=2)
        before_groups = {
            c.code for c in db.query(Course).filter(Course.qualification_id == source.id)
        }

        _dup(db, source, name="Copy")

        after = db.get(Qualification, source.id)
        assert after.name == "Cert IV Cyber"
        assert after.num_groups == 2
        assert (
            db.query(UnitQualification)
            .filter(UnitQualification.qualification_id == source.id)
            .count()
            == 2
        )
        assert {
            c.code for c in db.query(Course).filter(Course.qualification_id == source.id)
        } == before_groups

    def test_its_bookings_are_not_touched(self, db):
        source, units = _qual(db, "Cert IV Cyber", classes=1)
        course = db.query(Course).filter(Course.qualification_id == source.id).one()
        db.add(
            Booking(
                week_id=1, course_id=course.id, unit_id=units[0].id,
                day=0, start_slot=2, end_slot=6,
            )
        )
        db.commit()

        _dup(db, source, name="Copy")

        assert db.query(Booking).count() == 1
        assert db.query(Booking).one().course_id == course.id


class TestTheCopyGetsItsOwnGroups:
    def test_new_cohorts_are_created_under_the_copys_name(self, db):
        source, _ = _qual(db, "Cert IV Cyber", groups=2, classes=1)

        out = _dup(db, source, name="Cert IV Cyber 2027")

        new_groups = (
            db.query(Course)
            .filter(Course.qualification_id == out["qualification_id"])
            .all()
        )
        assert len(new_groups) == 2
        assert all(c.code.startswith("Cert IV Cyber 2027") for c in new_groups)
        assert out["num_groups"] == 2

    def test_each_new_group_holds_the_same_classes(self, db):
        source, units = _qual(db, "Cert IV Cyber", groups=2, classes=3)

        out = _dup(db, source, name="Copy")

        new_groups = (
            db.query(Course).filter(Course.qualification_id == out["qualification_id"]).all()
        )
        for c in new_groups:
            held = {
                cu.unit_id for cu in db.query(CourseUnit).filter(CourseUnit.course_id == c.id)
            }
            # Empty holding areas would mean adding every class to every group
            # by hand -- the retyping this feature removes.
            assert held == {u.id for u in units}
        assert out["groups_assigned"] == 6

    def test_the_copy_starts_with_an_empty_timetable(self, db):
        source, units = _qual(db, "Cert IV Cyber", classes=1)
        course = db.query(Course).filter(Course.qualification_id == source.id).one()
        db.add(
            Booking(
                week_id=1, course_id=course.id, unit_id=units[0].id,
                day=0, start_slot=2, end_slot=6,
            )
        )
        db.commit()

        out = _dup(db, source, name="Copy")

        new_ids = [
            c.id
            for c in db.query(Course).filter(Course.qualification_id == out["qualification_id"])
        ]
        assert db.query(Booking).filter(Booking.course_id.in_(new_ids)).count() == 0


class TestSettingsCarryOver:
    def test_the_schedule_period_and_its_windows_come_across(self, db):
        source, _ = _qual(db, "Night cert", period="night", classes=1)

        out = _dup(db, source, name="Night cert 2")

        copy = db.get(Qualification, out["qualification_id"])
        assert copy.schedule_period == "night"
        windows = (
            db.query(QualificationTimeWindow)
            .filter(QualificationTimeWindow.qualification_id == copy.id)
            .all()
        )
        assert windows, "a copy with no time windows would accept any slot"

    def test_block_delivery_settings_come_across(self, db):
        source, _ = _qual(db, "Block cert", classes=1)
        source.delivery_mode = "block"
        source.block_week_count = 2
        source.block_start_semester_week = 5
        db.commit()

        out = _dup(db, source, name="Block cert 2")

        copy = db.get(Qualification, out["qualification_id"])
        assert copy.delivery_mode == "block"
        assert copy.block_week_count == 2
        assert copy.block_start_semester_week == 5

    def test_online_student_counts_are_copied_not_moved(self, db):
        source, _ = _qual(db, "Cert IV Cyber", classes=1)
        staff = Staff(timetable_session_id=SID, name="A. Rivers", fte=1.0)
        db.add(staff)
        db.flush()
        db.add(
            StaffQualificationOnlineStudents(
                staff_id=staff.id, qualification_id=source.id, student_count=12
            )
        )
        db.commit()

        out = _dup(db, source, name="Copy")

        rows = db.query(StaffQualificationOnlineStudents).all()
        assert len(rows) == 2
        assert {r.qualification_id for r in rows} == {source.id, out["qualification_id"]}
        assert all(r.student_count == 12 for r in rows)

    def test_the_copy_is_not_put_in_the_sources_stage_family(self, db):
        parent, _ = _qual(db, "Diploma", classes=0)
        stage, _ = _qual(db, "Diploma Stg1", classes=1)
        stage.parent_qualification_id = parent.id
        db.commit()

        out = _dup(db, stage, name="Diploma Stg1 2027")

        # Inheriting the parent would make the copy show up as another stage of
        # a family that knows nothing about it.
        assert db.get(Qualification, out["qualification_id"]).parent_qualification_id is None


class TestNaming:
    def test_the_suggested_name_is_offered_when_none_is_given(self, db):
        source, _ = _qual(db, "Cert IV Cyber", classes=1)

        out = _dup(db, source)

        assert out["name"] == "Cert IV Cyber (copy)"

    def test_the_suggestion_steps_past_names_already_taken(self, db):
        source, _ = _qual(db, "Cert IV Cyber", classes=1)
        _dup(db, source)

        assert (
            duplicate_preview(db, timetable_session_id=SID, qualification_id=source.id)[
                "suggested_name"
            ]
            == "Cert IV Cyber (copy 2)"
        )

    def test_reusing_an_existing_name_is_refused(self, db):
        source, _ = _qual(db, "Cert IV Cyber", classes=1)

        with pytest.raises(QualificationDuplicateError, match="already exists"):
            _dup(db, source, name="Cert IV Cyber")

    def test_a_blank_name_is_refused(self, db):
        source, _ = _qual(db, "Cert IV Cyber", classes=1)

        with pytest.raises(QualificationDuplicateError, match="needs a name"):
            _dup(db, source, name="   ")

    def test_a_missing_qualification_is_not_found(self, db):
        with pytest.raises(LookupError):
            duplicate_qualification(db, timetable_session_id=SID, qualification_id=9999)

    def test_a_qualification_in_another_session_is_not_found(self, db):
        db.add(TimetableSession(id=2, organization_id=1, name="Other"))
        db.flush()
        other = Qualification(timetable_session_id=2, name="Elsewhere")
        db.add(other)
        db.commit()

        with pytest.raises(LookupError):
            duplicate_qualification(
                db, timetable_session_id=SID, qualification_id=other.id
            )


class TestPreview:
    def test_it_reports_what_the_copy_would_hold(self, db):
        source, _ = _qual(db, "Cert IV Cyber", groups=3, classes=4)

        out = duplicate_preview(db, timetable_session_id=SID, qualification_id=source.id)

        assert out["source_name"] == "Cert IV Cyber"
        assert out["class_count"] == 4
        assert out["num_groups"] == 3
        assert out["suggested_name"] == "Cert IV Cyber (copy)"

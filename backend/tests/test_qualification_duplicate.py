"""Copying a qualification without copying its classes.

The whole value of this is the thing it does *not* do: it must not create new
Class records. If it ever does, the duplicate's "ICTNWK540" and the original's
become two different classes, and the pair has to be folded back together in
the Classes tab -- which is the manual work this exists to avoid. Most of what
is asserted below is that the class rows are shared, and that the source is
left exactly as it was.

The other half is scope. A split qualification is several Qualification
records that the list shows as one row, so "duplicate this qualification" means
the whole stage family. Copying only the record that happened to be open would
produce a lone "Stg2" belonging to nothing.
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


def _split_family(db, stem: str, stage_names: list[str], *, classes_per_stage: int = 1):
    """A stage family shaped the way a stage split leaves one.

    Stage one points at itself, so every member shares one parent id — that is
    the equality test `family_qualifications` runs.
    """
    stages = []
    for i, name in enumerate(stage_names):
        q, units = _qual(db, name, groups=1, classes=classes_per_stage)
        stages.append((q, units))
    root = stages[0][0]
    for q, _ in stages:
        q.parent_qualification_id = root.id
    db.commit()
    return stages


class TestAWholeQualificationIsCopied:
    def test_every_stage_is_duplicated_not_just_the_open_one(self, db):
        _split_family(db, "Cert IV Cyber", ["Cert IV Cyber Stg1", "Cert IV Cyber Stg2"])

        out = duplicate_qualification(
            db,
            timetable_session_id=SID,
            qualification_id=db.query(Qualification).filter_by(name="Cert IV Cyber Stg1").one().id,
            name="Cert IV Cyber 2027",
        )

        assert out["stage_count"] == 2
        assert out["stage_names"] == ["Cert IV Cyber 2027 Stg1", "Cert IV Cyber 2027 Stg2"]

    def test_duplicating_from_a_later_stage_still_copies_the_whole_thing(self, db):
        _split_family(db, "Cert IV Cyber", ["Cert IV Cyber Stg1", "Cert IV Cyber Stg2"])
        stg2 = db.query(Qualification).filter_by(name="Cert IV Cyber Stg2").one()

        # The record that happens to be open is an implementation detail, so it
        # must not change what gets copied.
        out = duplicate_qualification(
            db, timetable_session_id=SID, qualification_id=stg2.id, name="Cert IV Cyber 2027"
        )

        assert out["stage_names"] == ["Cert IV Cyber 2027 Stg1", "Cert IV Cyber 2027 Stg2"]

    def test_the_copy_is_its_own_family(self, db):
        _split_family(db, "Cert IV Cyber", ["Cert IV Cyber Stg1", "Cert IV Cyber Stg2"])
        source_root = db.query(Qualification).filter_by(name="Cert IV Cyber Stg1").one()

        out = duplicate_qualification(
            db, timetable_session_id=SID, qualification_id=source_root.id, name="Copy",
        )

        copies = [
            db.query(Qualification).filter_by(name=n).one() for n in out["stage_names"]
        ]
        # Stage one points at itself, exactly as a split leaves it.
        assert copies[0].parent_qualification_id == copies[0].id
        assert {c.parent_qualification_id for c in copies} == {copies[0].id}
        # And has nothing to do with the family it came from.
        assert copies[0].id != source_root.id
        assert source_root.parent_qualification_id == source_root.id

    def test_each_stage_keeps_its_own_classes(self, db):
        stages = _split_family(
            db, "Cert IV Cyber", ["Cert IV Cyber Stg1", "Cert IV Cyber Stg2"],
        )
        out = duplicate_qualification(
            db, timetable_session_id=SID, qualification_id=stages[0][0].id, name="Copy",
        )

        for (source, units), copied_name in zip(stages, out["stage_names"]):
            copy = db.query(Qualification).filter_by(name=copied_name).one()
            linked = {
                uq.unit_id
                for uq in db.query(UnitQualification).filter(
                    UnitQualification.qualification_id == copy.id
                )
            }
            # Stage 2's classes must not end up on stage 1 of the copy.
            assert linked == {u.id for u in units}

    def test_no_new_class_records_across_the_family(self, db):
        _split_family(
            db, "Cert IV Cyber",
            ["Cert IV Cyber Stg1", "Cert IV Cyber Stg2"], classes_per_stage=3,
        )
        before = db.query(Unit).count()
        stg1 = db.query(Qualification).filter_by(name="Cert IV Cyber Stg1").one()

        duplicate_qualification(
            db, timetable_session_id=SID, qualification_id=stg1.id, name="Copy",
        )

        assert db.query(Unit).count() == before

    def test_the_source_family_is_untouched(self, db):
        stages = _split_family(db, "Cert IV Cyber", ["Cert IV Cyber Stg1", "Cert IV Cyber Stg2"])
        names_before = [q.name for q, _ in stages]

        duplicate_qualification(
            db, timetable_session_id=SID, qualification_id=stages[1][0].id, name="Copy",
        )

        assert [db.get(Qualification, q.id).name for q, _ in stages] == names_before

    def test_a_stage_renamed_off_the_stem_is_still_named_sensibly(self, db):
        _split_family(db, "Cert IV Cyber", ["Cert IV Cyber Stg1", "Evening intake"])
        stg1 = db.query(Qualification).filter_by(name="Cert IV Cyber Stg1").one()

        out = duplicate_qualification(
            db, timetable_session_id=SID, qualification_id=stg1.id, name="Cert IV Cyber 2027",
        )

        # No stem to swap, so it is qualified rather than left ambiguous.
        assert out["stage_names"] == [
            "Cert IV Cyber 2027 Stg1",
            "Cert IV Cyber 2027 — Evening intake",
        ]

    def test_a_stage_name_already_taken_is_stepped_past(self, db):
        _split_family(db, "Cert IV Cyber", ["Cert IV Cyber Stg1", "Cert IV Cyber Stg2"])
        _qual(db, "Copy Stg2", classes=0)  # in the way
        stg1 = db.query(Qualification).filter_by(name="Cert IV Cyber Stg1").one()

        out = duplicate_qualification(
            db, timetable_session_id=SID, qualification_id=stg1.id, name="Copy",
        )

        # Names are unique per session, so a collision has to be worked around
        # rather than allowed to fail mid-write.
        assert out["stage_names"] == ["Copy Stg1", "Copy Stg2 (2)"]

    def test_the_preview_describes_the_whole_family(self, db):
        _split_family(
            db, "Cert IV Cyber",
            ["Cert IV Cyber Stg1", "Cert IV Cyber Stg2"], classes_per_stage=2,
        )
        stg2 = db.query(Qualification).filter_by(name="Cert IV Cyber Stg2").one()

        out = duplicate_preview(db, timetable_session_id=SID, qualification_id=stg2.id)

        # Named for the qualification, not the stage that was open.
        assert out["source_name"] == "Cert IV Cyber"
        assert out["stage_count"] == 2
        assert out["class_count"] == 4
        assert out["num_groups"] == 2
        assert out["suggested_name"] == "Cert IV Cyber (copy)"

    def test_a_class_shared_by_two_stages_is_counted_once(self, db):
        stages = _split_family(db, "Cert IV Cyber", ["Cert IV Cyber Stg1", "Cert IV Cyber Stg2"])
        shared = stages[0][1][0]
        db.add(
            UnitQualification(unit_id=shared.id, qualification_id=stages[1][0].id)
        )
        db.commit()

        out = duplicate_preview(
            db, timetable_session_id=SID, qualification_id=stages[0][0].id
        )

        assert out["class_count"] == 2

    def test_an_unsplit_qualification_is_still_a_family_of_one(self, db):
        source, _ = _qual(db, "Standalone", classes=2)

        out = duplicate_qualification(
            db, timetable_session_id=SID, qualification_id=source.id, name="Standalone 2",
        )

        assert out["stage_count"] == 1
        assert out["name"] == "Standalone 2"
        # No family, so no self-referencing parent to invent.
        assert db.get(Qualification, out["qualification_id"]).parent_qualification_id is None


class TestStagesRelatedOnlyByName:
    """The shape imported data actually has.

    A qualification split inside the app leaves its stages sharing a parent id.
    One imported from a course study plan does not: "AdvDip IT Cyber Stg1" and
    "AdvDip IT Cyber Stg2" arrive as unrelated records, and the only thing
    saying they are one qualification is what they are called.
    """

    def test_stages_are_found_by_name_when_nothing_links_them(self, db):
        a, _ = _qual(db, "AdvDip IT Cyber Stg1", classes=2)
        b, _ = _qual(db, "AdvDip IT Cyber Stg2", classes=3)
        assert a.parent_qualification_id is None  # nothing links them

        out = _dup(db, a, name="AdvDip IT Cyber 2027")

        assert out["stage_count"] == 2
        assert out["stage_names"] == [
            "AdvDip IT Cyber 2027 Stg1",
            "AdvDip IT Cyber 2027 Stg2",
        ]
        assert out["class_count"] == 5

    def test_it_works_from_any_stage(self, db):
        _qual(db, "AdvDip IT Cyber Stg1", classes=1)
        b, _ = _qual(db, "AdvDip IT Cyber Stg2", classes=1)

        out = _dup(db, b, name="Copy")

        assert out["stage_names"] == ["Copy Stg1", "Copy Stg2"]

    def test_stage_order_comes_from_the_number_not_the_id(self, db):
        # Import order is not stage order: this session has "Stg 2" created
        # first, which is exactly what the dev data looks like.
        _qual(db, "CIV Net Stg 2", classes=1)
        first, _ = _qual(db, "CIV Net Stg1", classes=1)

        out = _dup(db, first, name="CIV Net 2027")

        assert out["stage_names"] == ["CIV Net 2027 Stg1", "CIV Net 2027 Stg 2"]

    @pytest.mark.parametrize(
        "names",
        [
            ("Dip Adv Prog AC21 STG1", "Dip Adv Prog AC21 STG2"),
            ("UX-BE Web Dev Skill Set - STG1", "UX-BE Web Dev Skill Set - STG2"),
            ("Cert2 ADT Stage1", "Cert2 ADT Stage2"),
        ],
    )
    def test_the_suffix_forms_that_appear_in_real_sessions(self, db, names):
        first, _ = _qual(db, names[0], classes=1)
        _qual(db, names[1], classes=1)

        assert _dup(db, first, name="X")["stage_count"] == 2

    def test_names_differing_by_more_than_the_suffix_are_left_alone(self, db):
        # "STG1 -GRP1" does not end in a stage suffix, so it strips to itself.
        # Two group variants of one stage are not two stages.
        first, _ = _qual(db, "Cert4 Cyber (BGT15) STG1 -GRP1", classes=1)
        _qual(db, "Cert4 Cyber (BGT15) STG1 -GRP2", classes=1)

        out = _dup(db, first, name="Copy")

        assert out["stage_count"] == 1
        assert out["name"] == "Copy"

    def test_a_qualification_with_no_stage_suffix_stands_alone(self, db):
        first, _ = _qual(db, "3D printing skillset", classes=1)
        _qual(db, "Intro AI Skillset", classes=1)

        assert _dup(db, first, name="Copy")["stage_count"] == 1

    def test_a_copy_suffix_is_not_mistaken_for_a_stage(self, db):
        first, _ = _qual(db, "BFF7 CIII IT", classes=1)
        _qual(db, "BFF7 CIII IT (2)", classes=1)

        assert _dup(db, first, name="Copy")["stage_count"] == 1

    def test_the_stages_it_found_are_reported_before_anything_is_made(self, db):
        first, _ = _qual(db, "AdvDip IT Cyber Stg1", classes=1)
        _qual(db, "AdvDip IT Cyber Stg2", classes=1)

        out = duplicate_preview(db, timetable_session_id=SID, qualification_id=first.id)

        # A name rule is a guess, so the dialog has to be able to show its work.
        assert out["source_name"] == "AdvDip IT Cyber"
        assert out["stage_names"] == ["AdvDip IT Cyber Stg1", "AdvDip IT Cyber Stg2"]
        assert out["suggested_name"] == "AdvDip IT Cyber (copy)"

    def test_each_stages_classes_stay_with_that_stage(self, db):
        a, a_units = _qual(db, "AdvDip IT Cyber Stg1", classes=2)
        _b, b_units = _qual(db, "AdvDip IT Cyber Stg2", classes=3)

        out = _dup(db, a, name="Copy")

        copies = [db.query(Qualification).filter_by(name=n).one() for n in out["stage_names"]]
        for copy, expected in zip(copies, (a_units, b_units)):
            linked = {
                uq.unit_id
                for uq in db.query(UnitQualification).filter(
                    UnitQualification.qualification_id == copy.id
                )
            }
            assert linked == {u.id for u in expected}

    def test_the_copy_becomes_a_real_family(self, db):
        a, _ = _qual(db, "AdvDip IT Cyber Stg1", classes=1)
        _qual(db, "AdvDip IT Cyber Stg2", classes=1)

        out = _dup(db, a, name="Copy")

        copies = [db.query(Qualification).filter_by(name=n).one() for n in out["stage_names"]]
        # Linked properly, unlike the imported originals -- so the list will
        # show the copy as the one qualification it is.
        assert copies[0].parent_qualification_id == copies[0].id
        assert copies[1].parent_qualification_id == copies[0].id
        # And the unlinked originals are still unlinked.
        assert db.get(Qualification, a.id).parent_qualification_id is None

    def test_no_new_class_records_across_a_name_family(self, db):
        a, _ = _qual(db, "AdvDip IT Cyber Stg1", classes=2)
        _qual(db, "AdvDip IT Cyber Stg2", classes=3)
        before = db.query(Unit).count()

        _dup(db, a, name="Copy")

        assert db.query(Unit).count() == before

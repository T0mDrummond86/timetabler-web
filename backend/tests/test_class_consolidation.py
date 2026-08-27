"""Folding duplicate classes into one.

The dangerous part is not the qualification links -- it is everything else
hanging off the rows being deleted. Two of the eight tables referencing a class
are ON DELETE SET NULL (bookings, lecturer preferences), so a careless delete
leaves placecards with no class rather than failing loudly. Another,
course_unit, cascades away and would quietly take the class out of a cohort's
holding area even though its placecards had been moved.

So most of what is asserted here is about the wreckage a delete would leave.
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

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from timetable.core.models import (  # noqa: E402
    Base,
    Booking,
    Course,
    CourseUnit,
    Qualification,
    Room,
    Semester,
    Staff,
    StaffCompetency,
    StaffPreference,
    Unit,
    UnitAllowedRoom,
    UnitQualification,
    Week,
)
from timetable.core.tenancy_models import Organization, TimetableSession  # noqa: E402

from app.services.class_consolidation import (  # noqa: E402
    ClassConsolidationError,
    consolidate_classes,
    suggestions_for_seed,
)

SID = 1


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores foreign keys unless told otherwise, and the whole point of
    # these tests is what the FK actions do on delete.
    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

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


def _unit(db, name: str, *, codes: str | None = None, marked: bool = False) -> Unit:
    u = Unit(
        timetable_session_id=SID,
        name=name,
        length_slots=4,
        component_codes=codes,
        common_class=1 if marked else 0,
    )
    db.add(u)
    db.flush()
    return u


def _qual(db, name: str) -> Qualification:
    q = Qualification(timetable_session_id=SID, name=name)
    db.add(q)
    db.flush()
    return q


def _course(db, code: str) -> Course:
    c = Course(timetable_session_id=SID, code=code)
    db.add(c)
    db.flush()
    return c


def _book(db, course: Course, unit: Unit, *, day=0, start=2, end=6) -> Booking:
    b = Booking(
        week_id=1, course_id=course.id, unit_id=unit.id,
        day=day, start_slot=start, end_slot=end,
    )
    db.add(b)
    db.flush()
    return b


def _fold(db, survivor: Unit, *absorbed: Unit) -> dict:
    return consolidate_classes(
        db,
        timetable_session_id=SID,
        survivor_id=survivor.id,
        absorbed_ids=[u.id for u in absorbed],
    )


class TestSuggestions:
    """Which classes to offer once one has been ticked.

    The question is "where else does this class run?", so the match is
    containment: a candidate must deliver every unit the ticked class delivers.
    It may deliver more -- the same class under a Diploma often bundles an extra
    unit, and excluding it for that would miss the duplicates worth folding.
    """

    def _ids(self, db, seed) -> set[int]:
        return set(
            suggestions_for_seed(
                db, timetable_session_id=SID, seed_unit_id=seed.id
            )["unit_ids"]
        )

    def test_a_class_with_the_same_units_is_suggested(self, db):
        seed = _unit(db, "ICTNWK540 CertIV", codes="ICTNWK540")
        same = _unit(db, "ICTNWK540 Dip", codes="ICTNWK540")
        db.commit()

        assert self._ids(db, seed) == {seed.id, same.id}

    def test_a_class_with_extra_units_is_suggested(self, db):
        seed = _unit(db, "Network security", codes="ICTNWK540")
        richer = _unit(db, "Network security (Dip)", codes="ICTNWK540, BSBCRT512")
        db.commit()

        assert self._ids(db, seed) == {seed.id, richer.id}

    def test_a_class_missing_one_of_the_units_is_not_suggested(self, db):
        seed = _unit(db, "Network security", codes="ICTNWK540, BSBCRT512")
        _unit(db, "Half of it", codes="ICTNWK540")
        db.commit()

        # Containment runs one way only: the candidate must cover the seed.
        assert self._ids(db, seed) == {seed.id}

    def test_an_unrelated_class_is_not_suggested(self, db):
        seed = _unit(db, "Network security", codes="ICTNWK540")
        _unit(db, "Something else", codes="ICTSAS527")
        db.commit()

        assert self._ids(db, seed) == {seed.id}

    def test_the_seed_is_in_its_own_result(self, db):
        seed = _unit(db, "Only one", codes="ICTNWK540")
        db.commit()

        # It is one of the classes being consolidated, so leaving it out would
        # make the count disagree with the ticks on screen.
        out = suggestions_for_seed(db, timetable_session_id=SID, seed_unit_id=seed.id)
        assert out["unit_ids"] == [seed.id]
        assert out["reason"] and "No other class" in out["reason"]

    def test_codes_match_regardless_of_case_and_spacing(self, db):
        seed = _unit(db, "One", codes="  ictnwk540 ")
        other = _unit(db, "Two", codes="ICTNWK540")
        db.commit()

        assert self._ids(db, seed) == {seed.id, other.id}

    def test_an_uncoded_seed_suggests_nothing_and_says_why(self, db):
        seed = _unit(db, "No codes", codes=None)
        _unit(db, "Has codes", codes="ICTNWK540")
        db.commit()

        out = suggestions_for_seed(db, timetable_session_id=SID, seed_unit_id=seed.id)

        # Every set contains the empty set, so matching on nothing would tick
        # the whole session.
        assert out["unit_ids"] == []
        assert "no unit codes" in out["reason"]

    def test_free_text_that_is_not_a_unit_code_is_ignored(self, db):
        # Real sessions have "LAB", "Robotics", "SfS" and lecturer surnames in
        # this field. They are not units, so they neither match nor exclude.
        seed = _unit(db, "One", codes="ICTNWK540, LAB")
        plain = _unit(db, "Two", codes="ICTNWK540")
        _unit(db, "Three", codes="LAB, Robotics")
        db.commit()

        assert self._ids(db, seed) == {seed.id, plain.id}

    def test_a_seed_of_only_free_text_suggests_nothing(self, db):
        seed = _unit(db, "One", codes="LAB, Robotics")
        _unit(db, "Two", codes="LAB")
        db.commit()

        out = suggestions_for_seed(db, timetable_session_id=SID, seed_unit_id=seed.id)
        assert out["unit_ids"] == []
        assert "no unit codes" in out["reason"]

    def test_the_shapes_real_codes_come_in_are_all_matched(self, db):
        for code in ("ICTNWK540", "VU23213", "MEM30031", "BSBWHS411A"):
            seed = _unit(db, f"A {code}", codes=code)
            other = _unit(db, f"B {code}", codes=code)
            db.commit()
            assert self._ids(db, seed) == {seed.id, other.id}, code

    def test_the_seed_codes_are_reported_for_the_dialog(self, db):
        seed = _unit(db, "One", codes="ictnwk540, bsbcrt512")
        db.commit()

        out = suggestions_for_seed(db, timetable_session_id=SID, seed_unit_id=seed.id)

        assert out["seed_name"] == "One"
        assert out["seed_codes"] == ["BSBCRT512", "ICTNWK540"]

    def test_a_class_from_another_session_never_matches(self, db):
        seed = _unit(db, "One", codes="ICTNWK540")
        db.add(TimetableSession(id=2, organization_id=1, name="Other"))
        db.flush()
        db.add(Unit(timetable_session_id=2, name="Elsewhere", component_codes="ICTNWK540"))
        db.commit()

        assert self._ids(db, seed) == {seed.id}

    def test_a_missing_seed_is_not_found(self, db):
        with pytest.raises(LookupError):
            suggestions_for_seed(db, timetable_session_id=SID, seed_unit_id=99999)


class TestQualificationLinks:
    def test_the_survivor_gains_the_absorbed_qualifications(self, db):
        cert, dip = _qual(db, "Cert IV"), _qual(db, "Diploma")
        keep, drop = _unit(db, "ICTNWK540 CertIV"), _unit(db, "ICTNWK540 Dip")
        db.add(UnitQualification(unit_id=keep.id, qualification_id=cert.id))
        db.add(UnitQualification(unit_id=drop.id, qualification_id=dip.id))
        db.commit()

        out = _fold(db, keep, drop)

        links = {
            uq.qualification_id
            for uq in db.query(UnitQualification).filter(UnitQualification.unit_id == keep.id)
        }
        assert links == {cert.id, dip.id}
        assert out["qualifications_gained"] == 1

    def test_a_shared_qualification_is_not_linked_twice(self, db):
        # unit_qualification has a composite primary key; inserting the row
        # again would be an integrity error, not a no-op.
        cert = _qual(db, "Cert IV")
        keep, drop = _unit(db, "A"), _unit(db, "B")
        db.add(UnitQualification(unit_id=keep.id, qualification_id=cert.id))
        db.add(UnitQualification(unit_id=drop.id, qualification_id=cert.id))
        db.commit()

        out = _fold(db, keep, drop)

        assert db.query(UnitQualification).filter(UnitQualification.unit_id == keep.id).count() == 1
        assert out["qualifications_gained"] == 0

    def test_three_classes_fold_into_one(self, db):
        quals = [_qual(db, f"Q{i}") for i in range(3)]
        units = [_unit(db, f"Class {i}") for i in range(3)]
        for q, u in zip(quals, units):
            db.add(UnitQualification(unit_id=u.id, qualification_id=q.id))
        db.commit()

        _fold(db, units[0], units[1], units[2])

        links = {
            uq.qualification_id
            for uq in db.query(UnitQualification).filter(UnitQualification.unit_id == units[0].id)
        }
        assert links == {q.id for q in quals}
        assert db.query(Unit).count() == 1


class TestNothingIsOrphaned:
    def test_placecards_move_and_none_are_left_classless(self, db):
        grp = _course(db, "Cert IV GrpA")
        keep, drop = _unit(db, "A"), _unit(db, "B")
        _book(db, grp, keep, day=0)
        _book(db, grp, drop, day=1)
        _book(db, grp, drop, day=2)
        db.commit()

        out = _fold(db, keep, drop)

        assert out["bookings_moved"] == 2
        assert db.query(Booking).filter(Booking.unit_id == keep.id).count() == 3
        # The failure this guards: ON DELETE SET NULL quietly leaving placecards
        # on the grid with no class behind them.
        assert db.query(Booking).filter(Booking.unit_id.is_(None)).count() == 0

    def test_the_cohorts_that_delivered_it_are_carried_across(self, db):
        a, b = _course(db, "GrpA"), _course(db, "GrpB")
        keep, drop = _unit(db, "A"), _unit(db, "B")
        db.add(CourseUnit(course_id=a.id, unit_id=keep.id))
        db.add(CourseUnit(course_id=b.id, unit_id=drop.id))
        db.commit()

        out = _fold(db, keep, drop)

        courses = {cu.course_id for cu in db.query(CourseUnit).filter(CourseUnit.unit_id == keep.id)}
        # Without this, GrpB loses the class from its holding area even though
        # its placecards were moved.
        assert courses == {a.id, b.id}
        assert out["groups_gained"] == 1

    def test_a_shared_cohort_is_not_linked_twice(self, db):
        a = _course(db, "GrpA")
        keep, drop = _unit(db, "A"), _unit(db, "B")
        db.add(CourseUnit(course_id=a.id, unit_id=keep.id))
        db.add(CourseUnit(course_id=a.id, unit_id=drop.id))
        db.commit()

        _fold(db, keep, drop)

        assert db.query(CourseUnit).filter(CourseUnit.unit_id == keep.id).count() == 1

    def test_lecturer_preferences_follow_the_class(self, db):
        staff = Staff(timetable_session_id=SID, name="A. Rivers", fte=1.0)
        db.add(staff)
        db.flush()
        keep, drop = _unit(db, "A"), _unit(db, "B")
        db.add(
            StaffPreference(
                staff_id=staff.id, priority=1, slot_number=1,
                class_name="B", unit_id=drop.id,
            )
        )
        db.commit()

        out = _fold(db, keep, drop)

        pref = db.query(StaffPreference).one()
        assert pref.unit_id == keep.id
        # Left as the lecturer wrote it -- rewriting would lose what they asked
        # for.
        assert pref.class_name == "B"
        assert out["preferences_moved"] == 1

    def test_the_absorbed_rows_are_gone(self, db):
        keep, drop = _unit(db, "A"), _unit(db, "B")
        db.commit()

        _fold(db, keep, drop)

        assert db.query(Unit).filter(Unit.id == drop.id).count() == 0
        assert db.query(Unit).filter(Unit.id == keep.id).count() == 1


class TestSurvivorIsUntouched:
    def test_its_own_settings_are_kept(self, db):
        keep = _unit(db, "A", codes="ICTNWK540")
        keep.length_slots = 8
        keep.required_capacity = 25
        drop = _unit(db, "B", codes="BSBCRT512")
        drop.length_slots = 2
        drop.required_capacity = 99
        db.commit()

        _fold(db, keep, drop)

        after = db.query(Unit).filter(Unit.id == keep.id).one()
        assert after.length_slots == 8
        assert after.required_capacity == 25
        # Settings are not combined: the absorbed codes go with it.
        assert after.component_codes == "ICTNWK540"

    def test_absorbed_rooms_and_competencies_go_with_it(self, db):
        room = Room(timetable_session_id=SID, code="B2.14", capacity=20)
        staff = Staff(timetable_session_id=SID, name="A. Rivers", fte=1.0)
        db.add_all([room, staff])
        db.flush()
        keep, drop = _unit(db, "A"), _unit(db, "B")
        db.add(UnitAllowedRoom(unit_id=drop.id, room_id=room.id))
        db.add(StaffCompetency(staff_id=staff.id, unit_id=drop.id))
        db.commit()

        _fold(db, keep, drop)

        # Deliberate: "survivor's settings only". Documented so the UI can warn.
        assert db.query(UnitAllowedRoom).count() == 0
        assert db.query(StaffCompetency).count() == 0

    def test_absorbed_unit_codes_can_be_carried_across_on_request(self, db):
        keep = _unit(db, "A", codes="ICTCYS402, ICTCYS407")
        drop = _unit(db, "B", codes="ICTSAS524, ICTCYS407")
        db.commit()

        out = consolidate_classes(
            db,
            timetable_session_id=SID,
            survivor_id=keep.id,
            absorbed_ids=[drop.id],
            merge_codes=True,
        )

        after = db.query(Unit).filter(Unit.id == keep.id).one()
        # The survivor's own spelling is left alone and the new code appended;
        # the code both already had is not repeated.
        assert after.component_codes == "ICTCYS402, ICTCYS407, ICTSAS524"
        assert out["codes_gained"] == ["ictsas524"]

    def test_carrying_codes_across_works_when_the_survivor_had_none(self, db):
        keep = _unit(db, "A", codes=None)
        drop = _unit(db, "B", codes="ICTSAS524")
        db.commit()

        consolidate_classes(
            db, timetable_session_id=SID, survivor_id=keep.id,
            absorbed_ids=[drop.id], merge_codes=True,
        )

        assert db.query(Unit).filter(Unit.id == keep.id).one().component_codes == "ICTSAS524"

    def test_the_mark_is_cleared_once_dealt_with(self, db):
        keep = _unit(db, "A", marked=True)
        drop = _unit(db, "B", marked=True)
        db.commit()

        _fold(db, keep, drop)

        assert db.query(Unit).filter(Unit.id == keep.id).one().common_class == 0


class TestOverlapsAreReported:
    def test_a_collision_created_by_the_move_is_counted(self, db):
        grp = _course(db, "GrpA")
        keep, drop = _unit(db, "A"), _unit(db, "B")
        _book(db, grp, keep, day=0, start=2, end=6)
        _book(db, grp, drop, day=0, start=4, end=8)  # overlaps
        db.commit()

        out = _fold(db, keep, drop)

        assert out["overlaps_created"] == 1

    def test_placecards_that_do_not_collide_are_not_counted(self, db):
        grp = _course(db, "GrpA")
        keep, drop = _unit(db, "A"), _unit(db, "B")
        _book(db, grp, keep, day=0, start=2, end=6)
        _book(db, grp, drop, day=0, start=6, end=10)  # touches, does not overlap
        _book(db, grp, drop, day=1, start=2, end=6)  # different day
        db.commit()

        assert _fold(db, keep, drop)["overlaps_created"] == 0

    def test_different_cohorts_at_the_same_time_do_not_collide(self, db):
        a, b = _course(db, "GrpA"), _course(db, "GrpB")
        keep, drop = _unit(db, "A"), _unit(db, "B")
        _book(db, a, keep, day=0, start=2, end=6)
        _book(db, b, drop, day=0, start=2, end=6)
        db.commit()

        assert _fold(db, keep, drop)["overlaps_created"] == 0


class TestRefusals:
    def test_a_single_class_is_refused(self, db):
        keep = _unit(db, "A")
        db.commit()

        with pytest.raises(ClassConsolidationError, match="at least two"):
            _fold(db, keep)

    def test_folding_a_class_into_itself_is_refused(self, db):
        keep = _unit(db, "A")
        db.commit()

        with pytest.raises(ClassConsolidationError, match="at least two"):
            consolidate_classes(
                db, timetable_session_id=SID, survivor_id=keep.id, absorbed_ids=[keep.id]
            )

    def test_a_class_from_another_session_is_not_found(self, db):
        db.add(TimetableSession(id=2, organization_id=1, name="Other"))
        db.flush()
        keep = _unit(db, "A")
        other = Unit(timetable_session_id=2, name="Elsewhere")
        db.add(other)
        db.commit()

        with pytest.raises(LookupError):
            _fold(db, keep, other)

    def test_a_missing_class_is_not_found(self, db):
        keep = _unit(db, "A")
        db.commit()

        with pytest.raises(LookupError):
            consolidate_classes(
                db, timetable_session_id=SID, survivor_id=keep.id, absorbed_ids=[99999]
            )

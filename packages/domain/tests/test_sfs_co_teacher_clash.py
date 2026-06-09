"""SFS co-teacher term-scoped staff clash detection."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from timetable.core.booking_staff import staff_ids_with_term_overlap
from timetable.core.models import Booking, Course, Staff, Unit, Week
from timetable.core.storage import init_db, make_engine
from timetable.core.validation import validate_bookings


@pytest.fixture
def session(tmp_path):
    eng = make_engine(Path(tmp_path) / "sfs_clash.db")
    init_db(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False)
    with S() as s:
        yield s


def _booking(session, *, staff, co=None, in_t1=1, in_t2=1, co_t1=None, co_t2=None, **kw):
    week = session.query(Week).first()
    course = kw.pop("course", None) or session.query(Course).first()
    unit = kw.pop("unit", None) or session.query(Unit).first()
    if co_t1 is None:
        co_t1 = in_t1 if co else 0
    if co_t2 is None:
        co_t2 = in_t2 if co else 0
    b = Booking(
        week_id=week.id,
        course_id=course.id,
        unit_id=unit.id,
        staff_id=staff.id,
        sfs_co_teacher_staff_id=co.id if co else None,
        sfs_co_teacher_in_term_1=co_t1 if co else 0,
        sfs_co_teacher_in_term_2=co_t2 if co else 0,
        in_term_1=in_t1,
        in_term_2=in_t2,
        day=kw.pop("day", 0),
        start_slot=kw.pop("start_slot", 0),
        end_slot=kw.pop("end_slot", 4),
        **kw,
    )
    session.add(b)
    session.flush()
    return b


def test_no_clash_when_co_teacher_terms_do_not_overlap(session):
    """Co-teacher T1 only + same lecturer primary T2 only → not a double booking."""
    week = session.query(Week).first()
    alice = Staff(name="Alice")
    bob = Staff(name="Bob")
    course = Course(code="G1")
    unit = Unit(name="U1", length_slots=4)
    session.add_all([alice, bob, course, unit])
    session.flush()
    b1 = _booking(session, staff=alice, co=bob, co_t1=1, co_t2=0, day=0)
    b2 = _booking(session, staff=bob, day=0, start_slot=0, end_slot=4, in_t1=0, in_t2=1)
    session.commit()
    assert staff_ids_with_term_overlap(b1, b2) == set()
    staff_clashes = [v for v in validate_bookings(session, week.id) if v.code == "staff_double_booking"]
    assert not staff_clashes


def test_clash_when_co_teacher_shares_term(session):
    week = session.query(Week).first()
    alice = Staff(name="Alice")
    bob = Staff(name="Bob")
    course = Course(code="G1")
    unit = Unit(name="U1", length_slots=4)
    session.add_all([alice, bob, course, unit])
    session.flush()
    b1 = _booking(session, staff=alice, co=bob, co_t1=1, co_t2=0, day=0)
    b2 = _booking(session, staff=bob, day=0, start_slot=0, end_slot=4, in_t1=1, in_t2=0)
    session.commit()
    assert bob.id in staff_ids_with_term_overlap(b1, b2)
    assert any(v.code == "staff_double_booking" for v in validate_bookings(session, week.id))

"""Tests for aSc Timetables 2012 XML import."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

import timetable.core.tenancy_models  # noqa: F401 — register web tenancy tables
from timetable.core.models import Base, Booking, Qualification, Room, Semester, Staff, Unit, Week
from timetable.core.storage import make_engine
from timetable.core.tenancy_models import Organization, TimetableSession
from timetable.io.asc_import import import_asc_export, is_asc_export_file
from timetable.io.asc_xml_import import is_asc_export_xml

_XML_SAMPLE = Path("/Users/tomdrummond/Downloads/asctt2012.xml")


def _write_minimal_asc_xml(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<timetable displayname="aSc Timetables 2012 XML">
  <teachers>
    <teacher id="T1" name="Ada Lovelace" short="AL"/>
  </teachers>
  <classrooms>
    <classroom id="R1" name="Room 101" short="R101"/>
  </classrooms>
  <classes>
    <class id="C1" name="Diploma Stage 1" short="DIP1"/>
  </classes>
  <subjects>
    <subject id="S1" name="Cataloguing" short="BSBINS305"/>
  </subjects>
  <lessons>
    <lesson id="L1" classids="C1" subjectid="S1" periodspercard="2"
            teacherids="T1" classroomids="R1"/>
  </lessons>
  <cards>
    <card lessonid="L1" classroomids="R1" period="1" days="100000" terms="11"/>
    <card lessonid="L1" classroomids="R1" period="2" days="100000" terms="11"/>
  </cards>
</timetable>
""",
        encoding="utf-8",
    )


@pytest.fixture
def session(tmp_path):
    eng = make_engine(tmp_path / "asc_xml.db")
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False)
    with S() as s:
        org = Organization(name="Test Org", slug=f"test-{tmp_path.name}")
        s.add(org)
        s.flush()
        ts = TimetableSession(organization_id=org.id, name="Test session")
        s.add(ts)
        s.flush()
        sem = Semester(
            timetable_session_id=ts.id,
            name="Semester 2, 2026",
            num_weeks=18,
            repeating=1,
        )
        s.add(sem)
        s.flush()
        s.add(Week(semester_id=sem.id, week_number=0, label="Repeating week"))
        s.commit()
        s.timetable_session_id = ts.id  # type: ignore[attr-defined]
        yield s


def test_is_asc_export_xml_detects_minimal(tmp_path):
    path = tmp_path / "asc.xml"
    _write_minimal_asc_xml(path)
    assert is_asc_export_xml(path) is True
    assert is_asc_export_file(path) is True


def test_is_asc_export_xml_rejects_empty(tmp_path):
    path = tmp_path / "empty.xml"
    path.write_text("<root/>", encoding="utf-8")
    assert is_asc_export_xml(path) is False


def test_import_minimal_asc_xml(session, tmp_path):
    path = tmp_path / "asc.xml"
    _write_minimal_asc_xml(path)
    rep = import_asc_export(session, path, timetable_session_id=session.timetable_session_id)

    assert rep.staff_created == 1
    assert rep.rooms_created == 1
    assert rep.qualifications_created == 1
    assert rep.classes_created == 1
    assert rep.lecturer_links_added == 1
    assert rep.room_links_added == 1
    assert rep.bookings_created == 1

    assert session.query(Staff).filter(Staff.name == "Ada Lovelace").one()
    assert session.query(Room).filter(Room.code == "R101").one()
    assert session.query(Qualification).filter(Qualification.name == "Diploma Stage 1").one()
    unit = session.query(Unit).one()
    assert unit.component_codes == "BSBINS305"
    assert unit.length_slots == 2
    booking = session.query(Booking).one()
    assert booking.day == 0
    assert booking.start_slot == 0
    assert booking.end_slot == 2


def test_import_asc_xml_sample_when_available(session):
    if not _XML_SAMPLE.is_file():
        pytest.skip("aSc XML sample not available")

    rep = import_asc_export(session, _XML_SAMPLE, timetable_session_id=session.timetable_session_id)

    assert rep.staff_created >= 5
    assert rep.rooms_created >= 5
    assert rep.qualifications_created >= 3
    assert rep.classes_created >= 10
    assert rep.bookings_created >= 10

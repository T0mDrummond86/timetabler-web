"""Tests for aSc Timetables 2012 XML import."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from timetable.core.models import Booking, Qualification, Room, Staff, Unit
from timetable.core.storage import init_db, make_engine
from timetable.io.asc_import import import_asc_export, is_asc_export_file
from timetable.io.asc_import import _asc_periods_to_slots
from timetable.io.asc_xml_import import _parse_asc_xml_period_map, is_asc_export_xml

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
    init_db(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False)
    with S() as s:
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
    rep = import_asc_export(session, path)

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
    assert booking.start_slot == 1
    assert booking.end_slot == 3


def _write_multi_cohort_asc_xml(path: Path) -> None:
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
    <class id="C2" name="Diploma Stage 2" short="DIP2"/>
  </classes>
  <subjects>
    <subject id="S1" name="Cataloguing" short="BSBINS305"/>
  </subjects>
  <lessons>
    <lesson id="L1" classids="C1,C2" subjectid="S1" periodspercard="2"
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


def test_import_multi_cohort_lesson_creates_booking_per_class(session, tmp_path):
    path = tmp_path / "multi.xml"
    _write_multi_cohort_asc_xml(path)
    rep = import_asc_export(session, path)

    assert rep.bookings_created == 2
    assert session.query(Booking).count() == 2
    quals = {q.name for q in session.query(Qualification).all()}
    assert quals == {"Diploma Stage 1", "Diploma Stage 2"}
    bookings = session.query(Booking).order_by(Booking.course_id).all()
    assert bookings[0].day == bookings[1].day == 0
    assert bookings[0].start_slot == bookings[1].start_slot == 1
    assert bookings[0].end_slot == bookings[1].end_slot == 3
    assert bookings[0].course_id != bookings[1].course_id


def test_import_multi_cohort_reimport_is_idempotent(session, tmp_path):
    path = tmp_path / "multi.xml"
    _write_multi_cohort_asc_xml(path)
    first = import_asc_export(session, path)
    second = import_asc_export(session, path)
    assert first.bookings_created == 2
    assert second.bookings_created == 2
    assert session.query(Booking).count() == 2


def test_import_multi_cohort_lesson_4103535120799b7b(session):
    """Combined LAB lesson must appear on every participating Dip cohort grid."""
    if not _XML_SAMPLE.is_file():
        pytest.skip("aSc XML sample not available")

    import xml.etree.ElementTree as ET

    from timetable.core.models import Course

    root = ET.parse(_XML_SAMPLE).getroot()
    lesson_id = "4103535120799B7B"

    def attr(e, n):
        return (e.get(n) or "").strip()

    class_names = {attr(c, "id"): attr(c, "name") for c in root.find("classes").findall("class")}
    lesson = next(
        l for l in root.find("lessons").findall("lesson") if attr(l, "id") == lesson_id
    )
    cohort_names = [class_names[cid] for cid in attr(lesson, "classids").split(",") if cid.strip()]
    assert len(cohort_names) == 4

    rep = import_asc_export(session, _XML_SAMPLE)
    assert rep.bookings_created > 0

    cards = [c for c in root.find("cards").findall("card") if attr(c, "lessonid") == lesson_id]
    assert cards
    day_pattern = attr(cards[0], "days")
    day_idx = next(i for i, ch in enumerate(day_pattern) if ch == "1")
    periods = sorted(int(float(attr(c, "period"))) for c in cards)
    from timetable.io.asc_xml_import import _parse_asc_xml_period_map
    from timetable.io.asc_import import _asc_periods_to_slots

    period_map = _parse_asc_xml_period_map(root)
    start_slot, end_slot = _asc_periods_to_slots(periods[0], periods[-1], period_map=period_map)

    for cohort in cohort_names:
        qual = session.query(Qualification).filter(Qualification.name == cohort).one()
        course = session.query(Course).filter(Course.qualification_id == qual.id).first()
        assert course is not None
        matches = (
            session.query(Booking)
            .filter(
                Booking.course_id == course.id,
                Booking.day == day_idx,
                Booking.start_slot == start_slot,
                Booking.end_slot == end_slot,
            )
            .count()
        )
        assert matches >= 1, f"{cohort} missing LAB booking on day {day_idx}"


DIP_COHORTS = [
    "Dip Adv Prog AC21 STG1",
    "Dip Adv Prog AC21 STG2",
    "Dip BE AC27 STG1",
    "Dip BE AC27 STG2",
    "Dip FE AC26 STG1",
    "Dip FE AC26 STG2",
]


def test_import_six_dip_cohorts_share_combined_lesson_days(session):
    """Each Dip cohort gets bookings on days where XML shows combined lessons."""
    if not _XML_SAMPLE.is_file():
        pytest.skip("aSc XML sample not available")

    import xml.etree.ElementTree as ET
    from collections import defaultdict

    from timetable.core.models import Course
    from timetable.io.asc_import import _asc_periods_to_slots
    from timetable.io.asc_xml_import import _merge_period_runs, _parse_asc_xml_period_map

    root = ET.parse(_XML_SAMPLE).getroot()

    def attr(e, n):
        return (e.get(n) or "").strip()

    class_names = {attr(c, "id"): attr(c, "name") for c in root.find("classes").findall("class")}
    cohort_ids = {cid for cid, name in class_names.items() if name in DIP_COHORTS}
    lessons_by_id = {attr(l, "id"): l for l in root.find("lessons").findall("lesson")}

    grouped: dict[tuple[str, str, str | None], list[int]] = defaultdict(list)
    for card in root.find("cards").findall("card"):
        grouped[(attr(card, "lessonid"), attr(card, "days"), attr(card, "terms") or None)].append(
            int(float(attr(card, "period")))
        )

    expected: dict[str, set[tuple[int, int, int]]] = {name: set() for name in DIP_COHORTS}
    period_map = _parse_asc_xml_period_map(root)
    for (lesson_id, days, _terms), periods in grouped.items():
        lesson = lessons_by_id.get(lesson_id)
        if lesson is None:
            continue
        cids = [x.strip() for x in attr(lesson, "classids").split(",") if x.strip()]
        if len(cids) < 2:
            continue
        involved = [class_names[c] for c in cids if c in cohort_ids]
        if len(involved) < 2:
            continue
        day_idx = next((i for i, ch in enumerate(days) if ch == "1"), None)
        if day_idx is None:
            continue
        for start_p, end_p in _merge_period_runs(periods):
            slot_range = _asc_periods_to_slots(start_p, end_p, period_map=period_map or None)
            if slot_range is None:
                continue
            for cohort in involved:
                expected[cohort].add((day_idx, slot_range[0], slot_range[1]))

    import_asc_export(session, _XML_SAMPLE)

    missing: list[str] = []
    for cohort, slots in expected.items():
        if not slots:
            continue
        qual = session.query(Qualification).filter(Qualification.name == cohort).one()
        course = session.query(Course).filter(Course.qualification_id == qual.id).first()
        assert course is not None
        booked = {
            (b.day, b.start_slot, b.end_slot)
            for b in session.query(Booking).filter(Booking.course_id == course.id).all()
        }
        for key in slots:
            if key not in booked:
                missing.append(f"{cohort} day={key[0]} slots={key[1]}-{key[2]}")

    assert not missing, "Missing combined-lesson bookings:\n" + "\n".join(missing[:20])


def test_asc_period_map_uses_xml_bell_times(tmp_path):
    path = tmp_path / "periods.xml"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<timetable displayname="aSc Timetables 2012 XML">
  <periods>
    <period period="5" starttime="10:30" endtime="11:00"/>
    <period period="9" starttime="12:30" endtime="13:00"/>
  </periods>
  <teachers><teacher id="T1" name="Ada" short="A"/></teachers>
  <classrooms><classroom id="R1" name="Room" short="R1"/></classrooms>
  <classes><class id="C1" name="Diploma" short="DIP"/></classes>
  <subjects><subject id="S1" name="Unit" short="U1"/></subjects>
  <lessons>
    <lesson id="L1" classids="C1" subjectid="S1" periodspercard="5"
            teacherids="T1" classroomids="R1"/>
  </lessons>
  <cards>
    <card lessonid="L1" classroomids="R1" period="5" days="100000" terms="11"/>
    <card lessonid="L1" classroomids="R1" period="6" days="100000" terms="11"/>
    <card lessonid="L1" classroomids="R1" period="7" days="100000" terms="11"/>
    <card lessonid="L1" classroomids="R1" period="8" days="100000" terms="11"/>
    <card lessonid="L1" classroomids="R1" period="9" days="100000" terms="11"/>
  </cards>
</timetable>
""",
        encoding="utf-8",
    )
    import xml.etree.ElementTree as ET

    period_map = _parse_asc_xml_period_map(ET.parse(path).getroot())
    slots = _asc_periods_to_slots(5, 9, period_map=period_map)
    assert slots == (5, 10)


def test_import_asc_xml_sample_when_available(session):
    if not _XML_SAMPLE.is_file():
        pytest.skip("aSc XML sample not available")

    rep = import_asc_export(session, _XML_SAMPLE)

    assert rep.staff_created >= 5
    assert rep.rooms_created >= 5
    assert rep.qualifications_created >= 3
    assert rep.classes_created >= 10
    assert rep.bookings_created >= 10

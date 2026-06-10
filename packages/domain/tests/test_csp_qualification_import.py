"""Tests for CSP (.docx) qualification import."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from sqlalchemy.orm import sessionmaker

from timetable.core.storage import init_db, make_engine
from timetable.core.models import Qualification, Unit, UnitQualification
from timetable.io.csp_qualification_import import (
    extract_csp_qualification_stages,
    import_qualifications_from_csp,
)

_CSP_SAMPLE = Path(
    "/Users/tomdrummond/Downloads/CSP_ICT50220 Diploma of Information Technology (AdvNetworking) V1.0.docx"
)


@pytest.fixture
def session(tmp_path):
    eng = make_engine(tmp_path / "csp.db")
    init_db(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False)
    with S() as s:
        yield s


def test_extract_ict50220_csp_sample():
    if not _CSP_SAMPLE.is_file():
        pytest.skip("CSP sample not available")
    stages = extract_csp_qualification_stages(_CSP_SAMPLE)
    assert len(stages) == 2
    assert stages[0].qualification_name.endswith("Semester 1")
    assert stages[1].qualification_name.endswith("Semester 2")

    s1_classes = {c.name: c for c in stages[0].classes}
    assert "Cyber Support" in s1_classes
    assert s1_classes["Cyber Support"].hours == 2.0
    assert set(s1_classes["Cyber Support"].unit_codes) == {"BSBXCS402", "ICTSAS527"}

    assert "Virtualisation & Cloud" in s1_classes
    assert len(s1_classes["Virtualisation & Cloud"].unit_codes) == 3

    s2 = {c.name: c for c in stages[1].classes}
    assert "Incident Response Planning" in s2
    assert len(s2["Incident Response Planning"].unit_codes) == 3


def test_import_csp_creates_two_qualifications_and_multi_unit_classes(session, tmp_path):
    if not _CSP_SAMPLE.is_file():
        pytest.skip("CSP sample not available")

    rep = import_qualifications_from_csp(session, _CSP_SAMPLE)
    assert rep.qualifications_created == 2
    assert rep.classes_created >= 10

    quals = session.query(Qualification).order_by(Qualification.name).all()
    assert len(quals) == 2
    assert any("Semester 1" in q.name for q in quals)
    assert any("Semester 2" in q.name for q in quals)

    cyber = session.query(Unit).filter_by(name="Cyber Support").one()
    assert "BSBXCS402" in (cyber.component_codes or "")
    assert "ICTSAS527" in (cyber.component_codes or "")
    assert cyber.length_slots == 4  # 2 hours

    qual_ids = {
        qid
        for (qid,) in session.query(UnitQualification.qualification_id)
        .filter_by(unit_id=cyber.id)
        .all()
    }
    assert len(qual_ids) == 1


def test_extract_csp_merged_class_column():
    doc = Document()
    table = doc.add_table(rows=3, cols=4)
    table.rows[0].cells[0].text = "Skill Set"
    table.rows[0].cells[1].text = "SIN"
    table.rows[0].cells[2].text = "TPN"
    table.rows[0].cells[3].text = "Title"
    table.rows[1].cells[0].text = "Shared Class | 3hrs"
    table.rows[1].cells[1].text = "AAA01"
    table.rows[1].cells[2].text = "VU12345"
    table.rows[2].cells[0].text = ""
    table.rows[2].cells[1].text = "AAA02"
    table.rows[2].cells[2].text = "ICT99999"

    bio = BytesIO()
    doc.save(bio)
    stages = extract_csp_qualification_stages(bio.getvalue(), path_hint=Path("CSP_Test Qual.docx"))
    assert len(stages) == 1
    assert len(stages[0].classes) == 1
    cls = stages[0].classes[0]
    assert cls.name == "Shared Class"
    assert cls.hours == 3.0
    assert cls.unit_codes == ["VU12345", "ICT99999"]

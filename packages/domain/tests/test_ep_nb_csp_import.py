"""Tests for EP-NB CSP (.xlsx) qualification import."""
from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy.orm import sessionmaker

import timetable.core.tenancy_models  # noqa: F401
from timetable.core.models import Base, Qualification, Semester, Unit, UnitQualification, Week
from timetable.core.storage import make_engine
from timetable.core.tenancy_models import Organization, TimetableSession
from timetable.io.ep_nb_csp_import import (
    extract_ep_nb_csp_stages,
    import_qualifications_from_ep_nb_csp,
    is_ep_nb_csp_workbook,
)

_EP_NB_SAMPLE = Path(
    "/Users/tomdrummond/Downloads/!2026 ICT40120 AC10 EP CSP - C4 Net v1.0.xlsx"
)


def _write_minimal_ep_nb(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = "ICT40120 - Test Qualification 2026"
    ws["B23"] = "Semester 1"
    ws["A24"] = "BB Shell"
    ws["B24"] = "Hrs in class"
    ws["F24"] = "Skill set/ description"
    ws["G24"] = "SIN"
    ws["H24"] = "TPN"
    ws["I24"] = "UoC(s) being assessed"
    ws["A25"] = "Cluster Alpha"
    ws["B25"] = 3
    ws["H25"] = "VU11111"
    ws["H26"] = "VU22222"
    ws["B38"] = "Semester 2"
    ws["A39"] = "BB Shell"
    ws["B39"] = "Hrs in class"
    ws["F39"] = "Skill set/ description"
    ws["G39"] = "SIN"
    ws["H39"] = "TPN"
    ws["I39"] = "UoC(s) being assessed"
    ws["A40"] = "???"
    ws["B40"] = 2
    ws["F40"] = "Beta Class"
    ws["H40"] = "ICT99999"
    wb.save(path)


@pytest.fixture
def session(tmp_path):
    eng = make_engine(tmp_path / "epnb.db")
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


def test_is_ep_nb_csp_workbook_detects_minimal(tmp_path):
    path = tmp_path / "epnb.xlsx"
    _write_minimal_ep_nb(path)
    assert is_ep_nb_csp_workbook(path) is True


def test_extract_minimal_ep_nb_stages(tmp_path):
    path = tmp_path / "epnb.xlsx"
    _write_minimal_ep_nb(path)
    stages = extract_ep_nb_csp_stages(path)
    assert len(stages) == 2
    assert stages[0].stage_label == "Semester 1"
    assert len(stages[0].classes) == 1
    assert stages[0].classes[0].unit_codes == ["VU11111", "VU22222"]
    assert stages[0].classes[0].hours == 3.0
    assert stages[1].classes[0].name == "Beta Class"


def test_import_minimal_ep_nb(session, tmp_path):
    path = tmp_path / "epnb.xlsx"
    _write_minimal_ep_nb(path)
    rep = import_qualifications_from_ep_nb_csp(
        session, path, timetable_session_id=session.timetable_session_id
    )
    assert rep.qualifications_created == 2
    assert rep.classes_created == 2
    assert session.query(Qualification).count() == 2
    unit = session.query(Unit).filter_by(name="Cluster Alpha").one()
    assert "VU11111" in (unit.component_codes or "")
    assert unit.length_slots == 6


def test_import_ep_nb_sample_when_available(session):
    if not _EP_NB_SAMPLE.is_file():
        pytest.skip("EP-NB CSP sample not available")

    stages = extract_ep_nb_csp_stages(_EP_NB_SAMPLE)
    assert len(stages) == 2
    s1_units = sum(len(c.unit_codes) for c in stages[0].classes)
    s2_units = sum(len(c.unit_codes) for c in stages[1].classes)
    assert s1_units >= 10
    assert s2_units >= 8

    cluster = next(c for c in stages[0].classes if "Introduction to Networks" in c.name)
    assert len(cluster.unit_codes) == 3
    assert cluster.hours == 5.0

    rep = import_qualifications_from_ep_nb_csp(
        session, _EP_NB_SAMPLE, timetable_session_id=session.timetable_session_id
    )
    assert rep.qualifications_created == 2
    assert rep.classes_created >= 15

    win = session.query(Unit).filter(Unit.name.ilike("%Windows Desktop%")).one()
    assert "ICTNWK422" in (win.component_codes or "")

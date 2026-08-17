"""The tutorial's generated sample files must survive the real importers.

These files exist so the second tutorial can teach the import procedures with
real documents. The only contract that matters is the round trip: whatever
``sample_files`` writes, the production import code reads back — so these tests
push the exact bytes through the real importers, not through mocks.
"""
from __future__ import annotations

import os
import sys
import tempfile
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
    Qualification,
    Staff,
    StaffAvailability,
    StaffPreference,
    Unit,
    UnitQualification,
)
from timetable.core.tenancy_models import Organization, TimetableSession  # noqa: E402
from timetable.io.csp_qualification_import import (  # noqa: E402
    import_qualifications_from_csp,
)
from timetable.io.lecturer_preferences_import import (  # noqa: E402
    import_lecturer_preferences,
)

from app.services.tutorial.sample_files import (  # noqa: E402
    SAMPLE_CSP_CLASS_COUNT,
    SAMPLE_CSP_QUALIFICATION,
    SAMPLE_PREFS,
    build_sample_csp_docx,
    build_sample_preferences_xlsx,
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


def _tmpfile(content: bytes, suffix: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


class TestSampleCsp:
    def test_imports_as_one_qualification_with_every_class(self, db):
        path = _tmpfile(build_sample_csp_docx(), ".docx")

        rep = import_qualifications_from_csp(db, path, timetable_session_id=SID)

        assert rep.qualifications_created == 1
        assert rep.classes_created == SAMPLE_CSP_CLASS_COUNT
        qual = db.query(Qualification).one()
        assert qual.name == SAMPLE_CSP_QUALIFICATION

    def test_multi_unit_class_keeps_both_codes(self, db):
        path = _tmpfile(build_sample_csp_docx(), ".docx")

        import_qualifications_from_csp(db, path, timetable_session_id=SID)

        unit = db.query(Unit).filter(Unit.name == "Networking Essentials").one()
        codes = (unit.component_codes or "").replace(" ", "")
        assert "VU23302" in codes and "VU23303" in codes
        # 3 hours → 6 half-hour slots.
        assert unit.length_slots == 6

    def test_every_class_links_to_the_qualification(self, db):
        path = _tmpfile(build_sample_csp_docx(), ".docx")

        import_qualifications_from_csp(db, path, timetable_session_id=SID)

        qual = db.query(Qualification).one()
        linked = (
            db.query(UnitQualification)
            .filter(UnitQualification.qualification_id == qual.id)
            .count()
        )
        assert linked == SAMPLE_CSP_CLASS_COUNT


class TestSamplePreferences:
    def _seed_staff(self, db):
        for name in SAMPLE_PREFS:
            db.add(Staff(timetable_session_id=SID, name=name))
        # One referenced class exists, proving the unit link resolves by name.
        db.add(
            Unit(
                timetable_session_id=SID,
                name="Network Security Fundamentals — VU23217",
                length_slots=4,
            )
        )
        db.commit()

    def test_fills_preferences_and_non_teaching_day(self, db):
        self._seed_staff(db)
        path = _tmpfile(build_sample_preferences_xlsx(), ".xlsx")

        rep = import_lecturer_preferences(db, path)

        assert rep.staff_updated == len(SAMPLE_PREFS)
        expected_rows = sum(len(prefs) for prefs, _ in SAMPLE_PREFS.values())
        assert rep.preferences_imported == expected_rows
        assert not rep.warnings

        for name, (prefs, _day) in SAMPLE_PREFS.items():
            staff = db.query(Staff).filter(Staff.name == name).one()
            assert staff.non_teaching_day == 4  # Friday
            stored = db.query(StaffPreference).filter_by(staff_id=staff.id).count()
            assert stored == len(prefs)

    def test_blocked_evenings_become_daytime_windows(self, db):
        self._seed_staff(db)
        path = _tmpfile(build_sample_preferences_xlsx(), ".xlsx")

        import_lecturer_preferences(db, path)

        staff = db.query(Staff).filter(Staff.name == "Keanu Reeves").one()
        windows = db.query(StaffAvailability).filter_by(staff_id=staff.id).all()
        # Evenings blocked on every day → one 08:00–18:00 window per weekday.
        assert len(windows) == 5
        assert {(w.day, w.start_slot, w.end_slot) for w in windows} == {
            (d, 0, 20) for d in range(5)
        }

    def test_unit_link_resolves_when_the_class_exists(self, db):
        self._seed_staff(db)
        path = _tmpfile(build_sample_preferences_xlsx(), ".xlsx")

        import_lecturer_preferences(db, path)

        linked = (
            db.query(StaffPreference)
            .filter(StaffPreference.unit_id.isnot(None))
            .count()
        )
        # Only the seeded class can link; the rest keep their names as text.
        assert linked == sum(
            1
            for prefs, _ in SAMPLE_PREFS.values()
            for _, _, cls in prefs
            if cls == "Network Security Fundamentals — VU23217"
        )

"""Exporting a qualification family back out as a CSP document.

The contract worth locking is the round trip: whatever the export writes, the
CSP importer must read back as the same classes. These also cover the parent
link the export relies on to find a family from any one of its stages.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from docx import Document

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
    Unit,
    UnitQualification,
)
from timetable.core.tenancy_models import Organization, TimetableSession  # noqa: E402
from timetable.io.csp_qualification_import import (  # noqa: E402
    extract_csp_qualification_stages,
)

from app.services.csp_export import (  # noqa: E402
    build_csp_export,
    family_qualifications,
    family_title,
)
from app.services.qualification_stages import (  # noqa: E402
    StagePlan,
    split_qualification_into_stages,
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


def _qual(db, name: str, groups: int = 1) -> Qualification:
    q = Qualification(timetable_session_id=SID, name=name, num_groups=groups)
    db.add(q)
    db.flush()
    return q


def _unit(db, name: str, qual: Qualification, *, slots: int = 4, codes: str = "") -> Unit:
    u = Unit(
        timetable_session_id=SID,
        name=name,
        length_slots=slots,
        component_codes=codes,
    )
    db.add(u)
    db.flush()
    db.add(UnitQualification(unit_id=u.id, qualification_id=qual.id))
    db.flush()
    return u


def _export(db, qualification_id: int) -> Path:
    path, _title = build_csp_export(
        db, timetable_session_id=SID, qualification_id=qualification_id
    )
    return path


class TestParentLink:
    def test_split_puts_every_stage_in_one_family(self, db):
        q = _qual(db, "Dip")
        a, b = _unit(db, "A", q), _unit(db, "B", q)
        db.commit()

        out = split_qualification_into_stages(
            db,
            timetable_session_id=SID,
            qualification_id=q.id,
            stages=[StagePlan("Dip Stg1", 1, (a.id,)), StagePlan("Dip Stg2", 1, (b.id,))],
        )

        ids = out["stage_qualification_ids"]
        parents = {
            db.get(Qualification, qid).parent_qualification_id for qid in ids
        }
        # Stage one points at itself, so the whole family shares one parent id.
        assert parents == {q.id}

    def test_family_is_reachable_from_any_stage(self, db):
        q = _qual(db, "Dip")
        a, b, c = _unit(db, "A", q), _unit(db, "B", q), _unit(db, "C", q)
        db.commit()

        out = split_qualification_into_stages(
            db,
            timetable_session_id=SID,
            qualification_id=q.id,
            stages=[
                StagePlan("Dip Stg1", 1, (a.id,)),
                StagePlan("Dip Stg2", 1, (b.id,)),
                StagePlan("Dip Stg3", 1, (c.id,)),
            ],
        )
        ids = out["stage_qualification_ids"]

        for qid in ids:
            family = family_qualifications(
                db, timetable_session_id=SID, qualification_id=qid
            )
            assert [f.id for f in family] == sorted(ids)

    def test_never_split_qualification_is_a_family_of_one(self, db):
        q = _qual(db, "Cert IV")
        _unit(db, "A", q)
        db.commit()

        family = family_qualifications(
            db, timetable_session_id=SID, qualification_id=q.id
        )
        assert [f.id for f in family] == [q.id]
        assert family_title(family) == "Cert IV"

    def test_family_title_drops_the_stage_suffix(self, db):
        q = _qual(db, "Dip of IT")
        a, b = _unit(db, "A", q), _unit(db, "B", q)
        db.commit()
        out = split_qualification_into_stages(
            db,
            timetable_session_id=SID,
            qualification_id=q.id,
            stages=[
                StagePlan("Dip of IT Stg1", 1, (a.id,)),
                StagePlan("Dip of IT Stg2", 1, (b.id,)),
            ],
        )
        family = family_qualifications(
            db, timetable_session_id=SID, qualification_id=out["stage_qualification_ids"][1]
        )
        assert family_title(family) == "Dip of IT"


class TestExportRoundTrip:
    def test_exports_one_table_per_stage(self, db):
        q = _qual(db, "Dip")
        a = _unit(db, "A", q, codes="X1")
        b = _unit(db, "B", q, codes="X2")
        c = _unit(db, "C", q, codes="X3")
        db.commit()
        out = split_qualification_into_stages(
            db,
            timetable_session_id=SID,
            qualification_id=q.id,
            stages=[
                StagePlan("Dip Stg1", 1, (a.id,)),
                StagePlan("Dip Stg2", 1, (b.id, c.id)),
            ],
        )

        path = _export(db, out["stage_qualification_ids"][0])
        stages = extract_csp_qualification_stages(path)

        assert len(stages) == 2
        assert [len(s.classes) for s in stages] == [1, 2]

    def test_reimport_reproduces_every_class(self, db):
        q = _qual(db, "Dip")
        a = _unit(db, "Networking", q, slots=4, codes="ICTNWK001, ICTNWK002")
        b = _unit(db, "Cyber Support", q, slots=3, codes="ICTCYS003")
        db.commit()
        out = split_qualification_into_stages(
            db,
            timetable_session_id=SID,
            qualification_id=q.id,
            stages=[StagePlan("Dip Stg1", 1, (a.id,)), StagePlan("Dip Stg2", 1, (b.id,))],
        )

        path = _export(db, out["stage_qualification_ids"][1])
        stages = extract_csp_qualification_stages(path)
        found = {c.name: c for s in stages for c in s.classes}

        assert set(found) == {"Networking", "Cyber Support"}
        # 2 slots to the hour, and multi-unit classes survive as continuation rows.
        assert found["Networking"].hours == 2
        assert found["Networking"].unit_codes == ["ICTNWK001", "ICTNWK002"]
        assert found["Cyber Support"].hours == 1.5
        assert found["Cyber Support"].unit_codes == ["ICTCYS003"]

    def test_unsplit_qualification_exports_as_a_single_stage(self, db):
        q = _qual(db, "Cert IV")
        _unit(db, "A", q, slots=2, codes="X1")
        _unit(db, "B", q, slots=2, codes="X2")
        db.commit()

        stages = extract_csp_qualification_stages(_export(db, q.id))

        assert len(stages) == 1
        assert {c.name for c in stages[0].classes} == {"A", "B"}

    def test_a_class_with_no_unit_codes_is_still_written_out(self, db):
        # The CSP format keys each row on its unit code, so a class carrying no
        # codes cannot come back through an import — but it must still appear in
        # the document, which is what a person reads it for.
        q = _qual(db, "Cert IV")
        _unit(db, "Work placement", q, slots=4, codes="")
        db.commit()

        doc = Document(str(_export(db, q.id)))
        cells = [c.text for t in doc.tables for r in t.rows for c in r.cells]

        assert any("Work placement" in text for text in cells)

    def test_export_of_a_missing_qualification_is_a_lookup_error(self, db):
        with pytest.raises(LookupError):
            build_csp_export(db, timetable_session_id=SID, qualification_id=9999)

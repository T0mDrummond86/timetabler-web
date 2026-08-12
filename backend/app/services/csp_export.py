"""Export a qualification family as a CSP .docx, one table per stage."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from timetable.core.models import Qualification, Unit, UnitQualification
from timetable.io.csp_qualification_export import ExportClass, ExportStage, write_csp_docx

# Two half-hour slots to the hour, matching the import's inverse.
SLOTS_PER_HOUR = 2

_STAGE_SUFFIX_RE = re.compile(r"\s*St(?:a?ge?)?\s*\d+\s*$", re.IGNORECASE)


def family_qualifications(
    db: Session, *, timetable_session_id: int, qualification_id: int
) -> list[Qualification]:
    """Every stage of the family this qualification belongs to, in stage order.

    A qualification that was never split is its own family of one, so the
    export works the same whether or not stages were ever created.
    """
    qual = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == timetable_session_id,
        )
        .one_or_none()
    )
    if qual is None:
        raise LookupError("Qualification not found")

    if not qual.parent_qualification_id:
        return [qual]

    root = qual.parent_qualification_id
    return (
        db.query(Qualification)
        .filter(
            Qualification.timetable_session_id == timetable_session_id,
            Qualification.parent_qualification_id == root,
        )
        .order_by(Qualification.name)
        .all()
    )


def family_title(stages: list[Qualification]) -> str:
    """The whole qualification's name, with the stage suffix taken back off."""
    if not stages:
        return "Qualification"
    if len(stages) == 1:
        return stages[0].name
    stem = _STAGE_SUFFIX_RE.sub("", stages[0].name).strip()
    return stem or stages[0].name


def _classes_for(db: Session, qualification_id: int) -> list[ExportClass]:
    units = (
        db.query(Unit)
        .join(UnitQualification, UnitQualification.unit_id == Unit.id)
        .filter(UnitQualification.qualification_id == qualification_id)
        .order_by(Unit.name)
        .all()
    )
    out: list[ExportClass] = []
    for u in units:
        codes = [c.strip() for c in (u.component_codes or "").split(",") if c.strip()]
        hours = (u.length_slots / SLOTS_PER_HOUR) if u.length_slots else None
        out.append(ExportClass(name=u.name or "", hours=hours, unit_codes=codes))
    return out


def build_csp_export(
    db: Session, *, timetable_session_id: int, qualification_id: int
) -> tuple[Path, str]:
    """Write the family to a temp .docx; returns the path and the family title."""
    quals = family_qualifications(
        db, timetable_session_id=timetable_session_id, qualification_id=qualification_id
    )
    title = family_title(quals)
    stages = [
        ExportStage(label=q.name, classes=_classes_for(db, q.id)) for q in quals
    ]
    tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    tmp.close()
    write_csp_docx(tmp.name, title=title, stages=stages)
    return Path(tmp.name), title

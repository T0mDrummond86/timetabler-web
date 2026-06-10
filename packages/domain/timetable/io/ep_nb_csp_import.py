"""Import qualifications + classes from NMTAFE EP-NB CSP Excel workbooks (.xlsx).

Layout (single sheet)
=====================
Row 1, column A: qualification title
  e.g. ``ICT40120 - AC10 - Certificate IV in Information Technology (Networking) 2026``

Semester bands are marked in column B (``Semester 1``, ``Semester 2``, …).
Each band has a header row containing ``BB Shell`` and ``TPN``, then data rows:

  A  BB Shell / class label (merged clusters leave this blank on continuation rows)
  B  Hrs in class (weekly contact hours for the class)
  F  Skill set / description (used when BB Shell is ``???``)
  H  TPN unit code
  I  Unit of competency title

Multi-unit classes share one BB Shell block; continuation rows only populate TPN (col H).
"""
from __future__ import annotations

import re
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from .csp_qualification_import import CspClass, CspStage
from .qualification_import import (
    QualImportReport,
    _create_kwargs,
    _parse_running_time,
    _scoped_filter_by,
    _text,
)
from ..core.models import Course, Qualification, Unit, UnitQualification
from ..core.qualification_schedule import SCHEDULE_PERIOD_DAY, replace_qualification_time_windows
from ..core.unit_brackets import apply_unit_bracket_fields_from_names, normalize_component_codes_commas

_COL_BB_SHELL = 0
_COL_HOURS = 1
_COL_SKILL_SET = 5
_COL_TPN = 7
_COL_UOC_TITLE = 8
_COL_SEMESTER = 1

_SEMESTER_RE = re.compile(r"^semester\s+(\d+)", re.IGNORECASE)
_PLACEHOLDER_SHELLS = frozenset({"???", "?", "-", "—"})


def _clean_cell(v) -> str | None:
    if v is None:
        return None
    s = str(v).replace("\xa0", " ").strip()
    return s or None


def _parse_hours(v) -> float | None:
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _is_header_row(row: tuple) -> bool:
    bb = _clean_cell(row[_COL_BB_SHELL] if len(row) > _COL_BB_SHELL else None)
    tpn = _clean_cell(row[_COL_TPN] if len(row) > _COL_TPN else None)
    return bool(bb and bb.lower() == "bb shell" and tpn and tpn.lower() == "tpn")


def _semester_label(row: tuple) -> str | None:
    val = _clean_cell(row[_COL_SEMESTER] if len(row) > _COL_SEMESTER else None)
    if not val:
        return None
    m = _SEMESTER_RE.match(val)
    if not m:
        return None
    return f"Semester {m.group(1)}"


def _qualification_title_from_sheet(ws) -> str:
    title = _text(ws.cell(row=1, column=1).value)
    if title:
        return title
    return "Imported qualification"


def _class_name_from_row(row: tuple, *, tpn: str) -> str:
    bb = _clean_cell(row[_COL_BB_SHELL] if len(row) > _COL_BB_SHELL else None)
    skill = _clean_cell(row[_COL_SKILL_SET] if len(row) > _COL_SKILL_SET else None)
    uoc = _clean_cell(row[_COL_UOC_TITLE] if len(row) > _COL_UOC_TITLE else None)

    if bb and bb.lower() not in _PLACEHOLDER_SHELLS:
        return bb
    if skill and skill.lower() not in _PLACEHOLDER_SHELLS:
        return skill.replace("\n", " ").strip()
    if uoc:
        return uoc.replace("\n", " ").strip()
    return tpn


def _is_subtotal_row(row: tuple) -> bool:
    bb = _clean_cell(row[_COL_BB_SHELL] if len(row) > _COL_BB_SHELL else None)
    if bb and bb.lower() in {"course total", "total"}:
        return True
    tpn = _clean_cell(row[_COL_TPN] if len(row) > _COL_TPN else None)
    if tpn:
        return False
    hrs = _parse_hours(row[_COL_HOURS] if len(row) > _COL_HOURS else None)
    # Semester summary rows (e.g. 19 hrs / 310 actual) have no TPN.
    return hrs is not None and hrs >= 10


def is_ep_nb_csp_workbook(path: str | Path) -> bool:
    """Return True when the workbook matches the EP-NB CSP Excel layout."""
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return False
    try:
        ws = wb.active
        title = _text(ws.cell(row=1, column=1).value)
        if not title:
            return False
        saw_semester = False
        saw_header = False
        for row in ws.iter_rows(min_row=2, max_row=min(ws.max_row or 0, 120), values_only=True):
            if _semester_label(row):
                saw_semester = True
            if _is_header_row(row):
                saw_header = True
            if saw_semester and saw_header:
                return True
        return False
    finally:
        wb.close()


def extract_ep_nb_csp_stages(path: str | Path) -> list[CspStage]:
    """Parse EP-NB CSP spreadsheet into per-semester qualification payloads."""
    wb = load_workbook(path, data_only=True)
    try:
        ws = wb.active
        base_title = _qualification_title_from_sheet(ws)
        stages: list[CspStage] = []
        pending_semester: str | None = None
        in_data = False
        current: CspClass | None = None
        current_classes: list[CspClass] = []

        def flush_stage() -> None:
            nonlocal current, current_classes, pending_semester, in_data
            if pending_semester and current_classes:
                stages.append(
                    CspStage(
                        qualification_name=f"{base_title} – {pending_semester}",
                        stage_label=pending_semester,
                        classes=current_classes,
                    )
                )
            current = None
            current_classes = []
            in_data = False

        for row in ws.iter_rows(min_row=2, values_only=True):
            sem = _semester_label(row)
            if sem:
                flush_stage()
                pending_semester = sem
                continue

            if _is_header_row(row):
                in_data = True
                current = None
                continue

            if not in_data or not pending_semester:
                continue

            if _is_subtotal_row(row):
                continue

            tpn = _clean_cell(row[_COL_TPN] if len(row) > _COL_TPN else None)
            if not tpn or tpn.lower() == "tpn":
                continue

            bb = _clean_cell(row[_COL_BB_SHELL] if len(row) > _COL_BB_SHELL else None)
            row_hours = _parse_hours(row[_COL_HOURS] if len(row) > _COL_HOURS else None)
            starts_new_class = bool(bb) or current is None

            if starts_new_class:
                name = _class_name_from_row(row, tpn=tpn)
                hours = row_hours
                key = (name, hours)
                if current is None or (current.name, current.hours) != key:
                    current = CspClass(name=name, hours=hours, unit_codes=[])
                    current_classes.append(current)
            elif current is None:
                name = _class_name_from_row(row, tpn=tpn)
                current = CspClass(name=name, hours=row_hours, unit_codes=[])
                current_classes.append(current)
            elif row_hours is not None and current.hours is None:
                current.hours = row_hours

            current.unit_codes.append(tpn)

        flush_stage()
        return stages
    finally:
        wb.close()


def import_qualifications_from_ep_nb_csp(
    session: Session,
    path: str | Path,
    *,
    timetable_session_id: int | None = None,
) -> QualImportReport:
    """Create/update qualifications and classes from an EP-NB CSP .xlsx file."""
    rep = QualImportReport()
    path = Path(path)
    if not is_ep_nb_csp_workbook(path):
        raise ValueError(
            "Workbook does not look like an EP-NB CSP export "
            "(expected qualification title, Semester bands, and BB Shell/TPN rows)."
        )

    stages = extract_ep_nb_csp_stages(path)
    if not stages:
        rep.warnings.append(f"No EP-NB CSP semester data found in {path.name}")
        return rep

    for stage in stages:
        qual_name = stage.qualification_name
        qual = _scoped_filter_by(
            session, Qualification, timetable_session_id, name=qual_name
        ).first()
        if qual is None:
            qual = Qualification(
                **_create_kwargs(
                    Qualification,
                    timetable_session_id,
                    name=qual_name,
                    num_groups=1,
                    schedule_period=SCHEDULE_PERIOD_DAY,
                )
            )
            session.add(qual)
            session.flush()
            replace_qualification_time_windows(session, qual)
            rep.qualifications_created += 1
            default_course_code = f"{qual.name} GrpA"
            existing_course = _scoped_filter_by(
                session, Course, timetable_session_id, code=default_course_code
            ).first()
            if existing_course is None:
                session.add(
                    Course(
                        **_create_kwargs(
                            Course,
                            timetable_session_id,
                            code=default_course_code,
                            qualification_id=qual.id,
                        )
                    )
                )
                rep.courses_created += 1
            elif existing_course.qualification_id != qual.id:
                existing_course.qualification_id = qual.id
        else:
            rep.qualifications_linked += 1

        for cls in stage.classes:
            storage_name = cls.name.strip()
            if not storage_name:
                continue

            component_codes = normalize_component_codes_commas(", ".join(cls.unit_codes))
            existing_unit = _scoped_filter_by(
                session, Unit, timetable_session_id, name=storage_name
            ).first()
            if existing_unit is None:
                unit = Unit(
                    **_create_kwargs(
                        Unit,
                        timetable_session_id,
                        name=storage_name,
                        component_codes=component_codes,
                    )
                )
                session.add(unit)
                session.flush()
                rep.classes_created += 1
            else:
                unit = existing_unit
                rep.classes_updated += 1

            if component_codes and not (unit.component_codes or "").strip():
                unit.component_codes = component_codes
            elif component_codes:
                merged = normalize_component_codes_commas(
                    f"{unit.component_codes}, {component_codes}"
                )
                if merged and merged != (unit.component_codes or "").strip():
                    unit.component_codes = merged

            if cls.hours is not None and not unit.length_slots:
                slots = _parse_running_time(str(cls.hours))
                if slots:
                    unit.length_slots = slots

            link = (
                session.query(UnitQualification)
                .filter_by(unit_id=unit.id, qualification_id=qual.id)
                .first()
            )
            if link is None:
                session.add(UnitQualification(unit_id=unit.id, qualification_id=qual.id))
                rep.class_qual_links_added += 1

    apply_unit_bracket_fields_from_names(session, timetable_session_id=timetable_session_id)
    session.commit()
    return rep

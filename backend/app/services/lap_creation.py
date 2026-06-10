"""Learning & Assessment Plan upload and lecturer sync."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from timetable.core.double_session import session_part_durations, unit_has_double_session
from timetable.core.lap_lecturers import lap_lecturer_fields_for_unit, lap_lecturers_for_unit
from timetable.core.models import Unit, UnitLap
from timetable.io.lap_docx import build_export_lap, is_lap_document

from .timetable_grid import get_repeating_week


def list_lap_rows(db: Session, *, timetable_session_id: int) -> list[dict]:
    week = get_repeating_week(db, timetable_session_id)
    week_id = week.id if week else None
    units = (
        db.query(Unit)
        .options(joinedload(Unit.lap))
        .filter(Unit.timetable_session_id == timetable_session_id)
        .order_by(Unit.name)
        .all()
    )
    rows: list[dict] = []
    for unit in units:
        lecturer_name = ""
        if week_id is not None:
            lecturer_name = lap_lecturer_fields_for_unit(db, unit, week_id=week_id).get("name", "")
        lap = unit.lap
        rows.append(
            {
                "unit_id": unit.id,
                "unit_name": unit.name,
                "component_codes": unit.component_codes,
                "has_lap": lap is not None,
                "original_filename": lap.original_filename if lap else None,
                "uploaded_at": lap.uploaded_at.isoformat() if lap and lap.uploaded_at else None,
                "timetable_lecturer_name": lecturer_name,
            }
        )
    return rows


def save_lap_upload(
    db: Session,
    *,
    timetable_session_id: int,
    unit_id: int,
    filename: str,
    content: bytes,
) -> UnitLap:
    if not filename.lower().endswith(".docx"):
        raise ValueError("Please upload a Word .docx file")
    if not is_lap_document(io.BytesIO(content)):
        raise ValueError(
            "This does not look like a Learning & Assessment Plan (footer code F122A14)"
        )
    unit = (
        db.query(Unit)
        .filter(Unit.id == unit_id, Unit.timetable_session_id == timetable_session_id)
        .first()
    )
    if unit is None:
        raise LookupError("Class not found")
    row = db.get(UnitLap, unit_id)
    if row is None:
        row = UnitLap(
            unit_id=unit_id,
            timetable_session_id=timetable_session_id,
            original_filename=filename,
            content=content,
        )
        db.add(row)
    else:
        row.original_filename = filename
        row.content = content
        row.uploaded_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def delete_lap(db: Session, *, timetable_session_id: int, unit_id: int) -> None:
    row = (
        db.query(UnitLap)
        .filter(
            UnitLap.unit_id == unit_id,
            UnitLap.timetable_session_id == timetable_session_id,
        )
        .first()
    )
    if row is None:
        raise LookupError("No LAP uploaded for this class")
    db.delete(row)
    db.commit()


def _lap_session_hours(unit: Unit) -> dict[int, str]:
    if not unit_has_double_session(unit):
        return {}
    first_slots, second_slots = session_part_durations(unit)
    return {1: _slots_to_hours(first_slots), 2: _slots_to_hours(second_slots)}


def _slots_to_hours(slots: int) -> str:
    hours = slots / 2
    return str(int(hours)) if hours == int(hours) else str(hours)


def build_updated_lap(
    db: Session,
    *,
    timetable_session_id: int,
    unit_id: int,
    delivery_period: str | None = None,
) -> tuple[bytes, str]:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    unit = (
        db.query(Unit)
        .options(joinedload(Unit.lap))
        .filter(Unit.id == unit_id, Unit.timetable_session_id == timetable_session_id)
        .first()
    )
    if unit is None or unit.lap is None:
        raise LookupError("No LAP uploaded for this class")
    lecturers = lap_lecturers_for_unit(db, unit, week_id=week.id)
    if not lecturers:
        raise ValueError("This class has no lecturer assigned on the timetable yet")
    updated = build_export_lap(
        unit.lap.content,
        lecturers,
        session_hours=_lap_session_hours(unit),
        delivery_period=delivery_period,
    )
    stem = unit.lap.original_filename
    if stem.lower().endswith(".docx"):
        stem = stem[:-5]
    filename = f"{stem} (updated).docx"
    return updated, filename


def build_updated_lap_zip(
    db: Session,
    *,
    timetable_session_id: int,
    delivery_period: str | None = None,
) -> tuple[bytes, str]:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    laps = (
        db.query(UnitLap)
        .options(joinedload(UnitLap.unit))
        .filter(UnitLap.timetable_session_id == timetable_session_id)
        .all()
    )
    if not laps:
        raise LookupError("No LAPs uploaded for this session")
    buf = io.BytesIO()
    written = 0
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for lap in laps:
            unit = lap.unit
            if unit is None:
                continue
            lecturers = lap_lecturers_for_unit(db, unit, week_id=week.id)
            if not lecturers:
                continue
            updated = build_export_lap(
                lap.content,
                lecturers,
                session_hours=_lap_session_hours(unit),
                delivery_period=delivery_period,
            )
            safe_name = "".join(c if c.isalnum() or c in " -_." else "_" for c in unit.name)
            stem = lap.original_filename
            if stem.lower().endswith(".docx"):
                stem = stem[:-5]
            zf.writestr(f"{safe_name} — {stem} (updated).docx", updated)
            written += 1
    if written == 0:
        raise ValueError("No uploaded LAPs have a lecturer assigned on the timetable")
    return buf.getvalue(), "laps_updated.zip"

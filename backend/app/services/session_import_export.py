"""Import/export timetable sessions (desktop-compatible backup payloads)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from timetable.io.backup_payload import read_backup_payload

from .session_data import restore_session, serialize_session
from .violation_dismissals import clear_all_dismissals


def import_workbook(db: Session, timetable_session_id: int, file_path: str) -> dict[str, int | str]:
    payload = read_backup_payload(file_path)
    counts = restore_session(db, timetable_session_id, payload)
    clear_all_dismissals(db, timetable_session_id=timetable_session_id)
    db.commit()
    return {**counts, "source": "xlsm"}


def import_qualifications_workbook(db: Session, timetable_session_id: int, file_path: str) -> dict:
    from timetable.io.qualification_import import import_qualifications_from_template

    rep = import_qualifications_from_template(db, file_path)
    clear_all_dismissals(db, timetable_session_id=timetable_session_id)
    db.commit()
    return {
        "qualifications_created": rep.qualifications_created,
        "qualifications_linked": rep.qualifications_linked,
        "classes_created": rep.classes_created,
        "classes_updated": rep.classes_updated,
        "courses_created": rep.courses_created,
        "class_qual_links_added": rep.class_qual_links_added,
        "room_links_added": rep.room_links_added,
        "lecturer_links_added": rep.lecturer_links_added,
        "warnings": rep.warnings,
        "source": "qualifications",
    }


def import_lecturer_preferences_workbook(db: Session, timetable_session_id: int, file_path: str) -> dict:
    from timetable.io.lecturer_preferences_import import import_lecturer_preferences

    rep = import_lecturer_preferences(db, file_path)
    clear_all_dismissals(db, timetable_session_id=timetable_session_id)
    db.commit()
    return {
        "staff_updated": rep.staff_updated,
        "preferences_imported": rep.preferences_imported,
        "avail_windows_written": rep.avail_windows_written,
        "warnings": rep.warnings,
        "source": "lecturer_preferences",
    }


def import_overall_visual_workbook(db: Session, timetable_session_id: int, file_path: str) -> dict:
    from timetable.io.overall_visual_import import import_overall_visual

    rep = import_overall_visual(db, file_path)
    clear_all_dismissals(db, timetable_session_id=timetable_session_id)
    db.commit()
    return {
        "bookings_written": rep.bookings_created,
        "courses_created": rep.courses_touched,
        "qualifications_created": rep.qualifications_created,
        "units_created": rep.units_created,
        "warnings": rep.warnings,
        "source": "overall_visual",
    }


def import_json_payload(
    db: Session, timetable_session_id: int, payload: dict
) -> dict[str, int | str]:
    counts = restore_session(db, timetable_session_id, payload)
    db.commit()
    return {**counts, "source": "json"}


def export_json(db: Session, timetable_session_id: int) -> dict:
    return serialize_session(db, timetable_session_id)


def save_upload_to_temp(upload_bytes: bytes, suffix: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(upload_bytes)
    tmp.close()
    return tmp.name


def cleanup_temp(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass

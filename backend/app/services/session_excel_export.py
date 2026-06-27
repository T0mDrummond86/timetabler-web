"""Excel export helpers for web API (wraps domain IO writers)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from timetable.io.admin_export import resolve_admin_template_path, write_admin_export
from timetable.io.changelog_export import write_change_log_xlsx
from timetable.io.lecturer_preferences_template import write_lecturer_preferences_template
from timetable.io.staff_export import write_staff_tab_xlsx
from timetable.io.xlsm_export import write_fresh, write_into_template
from timetable.io.xlsm_export_v2 import V2_TEMPLATE_PATH, write_v2

from timetable.core.change_log_data import gather_timetabling_change_log_display_rows

from .export_filenames import session_export_filename, timetable_session_name
from .timetable_grid import get_repeating_week


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _export_kwargs(db: Session, timetable_session_id: int) -> dict:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    return {
        "week_id": week.id,
        "timetable_session_id": timetable_session_id,
    }


def export_timetable_xlsx(
    db: Session,
    *,
    timetable_session_id: int,
    variant: str = "fresh",
    colour_by_class: bool = True,
) -> tuple[bytes, str, str]:
    """Return (bytes, filename, media_type)."""
    session_name = timetable_session_name(db, timetable_session_id)
    kw = _export_kwargs(db, timetable_session_id)

    suffix = ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        out = Path(tmp.name)

    try:
        if variant == "v2":
            if not V2_TEMPLATE_PATH.is_file():
                raise FileNotFoundError(
                    f"v2 export template not found at {V2_TEMPLATE_PATH}. "
                    "Ensure packages/domain/templates/export_v2_base.xlsm is deployed."
                )
            write_v2(
                db,
                out.with_suffix(".xlsm"),
                colour_by_class=colour_by_class,
                **kw,
            )
            out = out.with_suffix(".xlsm")
            suffix = ".xlsm"
        elif variant == "template":
            from timetable.bundle_paths import resource_path

            tpl = resource_path("templates", "timetable_export.xlsm")
            if tpl.is_file():
                write_into_template(
                    db,
                    tpl,
                    out.with_suffix(".xlsm"),
                    colour_by_class=colour_by_class,
                    **kw,
                )
                out = out.with_suffix(".xlsm")
                suffix = ".xlsm"
            else:
                write_fresh(db, out, **kw)
        else:
            write_fresh(db, out, **kw)
        filename = session_export_filename(session_name, suffix)
        media = (
            "application/vnd.ms-excel.sheet.macroEnabled.12"
            if suffix == ".xlsm"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        return _read_bytes(out), filename, media
    finally:
        out.unlink(missing_ok=True)


def export_admin_xlsx(
    db: Session,
    *,
    timetable_session_id: int,
    changed_only: bool = False,
) -> tuple[bytes, str]:
    session_name = timetable_session_name(db, timetable_session_id)
    kw = _export_kwargs(db, timetable_session_id)
    tpl = resolve_admin_template_path()
    suffix = ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        out = Path(tmp.name)
    try:
        write_admin_export(db, out, tpl, changed_only=changed_only, **kw)
        label = "admin export changes" if changed_only else "admin export"
        filename = session_export_filename(session_name, suffix, label=label)
        return _read_bytes(out), filename
    finally:
        out.unlink(missing_ok=True)


def export_staff_tab(db: Session, *, timetable_session_id: int) -> tuple[bytes, str]:
    session_name = timetable_session_name(db, timetable_session_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        out = Path(tmp.name)
    try:
        write_staff_tab_xlsx(db, out)
        return _read_bytes(out), session_export_filename(session_name, ".xlsx", label="staff tab")
    finally:
        out.unlink(missing_ok=True)


def export_change_log_xlsx_bytes(db: Session, *, timetable_session_id: int) -> tuple[bytes, str]:
    session_name = timetable_session_name(db, timetable_session_id)
    rows = gather_timetabling_change_log_display_rows(
        db,
        timetable_session_id=timetable_session_id,
        resolved=True,
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        out = Path(tmp.name)
    try:
        write_change_log_xlsx(out, rows)
        return _read_bytes(out), session_export_filename(session_name, ".xlsx", label="change log")
    finally:
        out.unlink(missing_ok=True)


def export_lecturer_preferences_template(db: Session, *, timetable_session_id: int) -> tuple[bytes, str]:
    session_name = timetable_session_name(db, timetable_session_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        out = Path(tmp.name)
    try:
        write_lecturer_preferences_template(db, out)
        return _read_bytes(out), session_export_filename(
            session_name,
            ".xlsx",
            label="lecturer preferences",
        )
    finally:
        out.unlink(missing_ok=True)

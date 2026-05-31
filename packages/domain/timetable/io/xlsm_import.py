"""Import a workbook by restoring embedded backup payload only."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .backup_payload import BACKUP_SHEET_NAME, deserialize, read_backup_payload


@dataclass
class ImportReport:
    courses: int = 0
    staff: int = 0
    rooms: int = 0
    bookings: int = 0
    qualifications: int = 0
    skipped_cells: int = 0
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


def import_overall(
    session: Session,
    xlsm_path: str,
    semester_name: str | None = None,
) -> ImportReport:
    """Import only from embedded ``__timetable_data__`` backup sheet."""
    del semester_name  # kept for API compatibility with previous callers
    payload = read_backup_payload(xlsm_path)
    deserialize(session, payload)
    report = ImportReport(
        courses=len(payload.get("courses", [])),
        staff=len(payload.get("staff", [])),
        rooms=len(payload.get("rooms", [])),
        bookings=len(payload.get("bookings", [])),
    )
    report.warnings.append("Restored from embedded backup data")
    return report


def import_v2(
    session: Session,
    xlsm_path: str,
) -> ImportReport:
    """Restore a session from an Export v2 workbook (embedded backup sheet)."""
    return import_overall(session, xlsm_path)


def import_admin(
    session: Session,
    xlsm_path: str,
) -> ImportReport:
    """Restore a session from an Admin export workbook (embedded backup sheet)."""
    return import_overall(session, xlsm_path)

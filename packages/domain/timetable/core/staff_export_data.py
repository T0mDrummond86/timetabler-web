"""Assemble Staff-tab data for Excel export (mirrors Staff editor columns)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Staff
from .staff_hours import (
    lecturing_hours_from_fte,
    staff_hours_snapshot_for_bookings,
    staff_hours_snapshots_by_staff_id,
    staff_tab_total_hours,
)

# Keep aligned with ``StaffEditor.columns`` in ``timetable.ui.editors``.
STAFF_TAB_EXPORT_HEADERS = (
    "Lecturer",
    "FTE",
    "Lecturing hours",
    "In-class timetabled hours",
    "Variance",
    "Bulk online (detail)",
    "Bulk online hrs (avg)",
    "Development & project",
    "Development & project description",
    "PD run training",
    "Supervision",
    "Total",
)


def _float_cell(v: float | None) -> str:
    return "" if v is None else f"{float(v):g}"


def gather_staff_tab_main_rows(session: Session) -> list[dict[str, str]]:
    """One dict per lecturer; keys match ``STAFF_TAB_EXPORT_HEADERS``."""
    snap_map = staff_hours_snapshots_by_staff_id(session)
    out: list[dict[str, str]] = []
    for s in session.query(Staff).order_by(Staff.name).all():
        snap = snap_map.get(s.id) or staff_hours_snapshot_for_bookings([])
        lh = lecturing_hours_from_fte(s.fte)
        variance: float | None = None
        if lh is not None:
            variance = staff_tab_total_hours(s, snap) - lh
        row = {
            "Lecturer": s.name or "",
            "FTE": _float_cell(getattr(s, "fte", None)),
            "Lecturing hours": "" if lh is None else f"{lh:.2f}",
            "In-class timetabled hours": f"{snap.regular_avg:.2f}",
            "Variance": "" if variance is None else f"{variance:.2f}",
            "Bulk online (detail)": snap.online_breakdown or "",
            "Bulk online hrs (avg)": f"{snap.online_avg:.2f}",
            "Development & project": _float_cell(getattr(s, "development_project_hours", None)),
            "Development & project description": (
                (getattr(s, "development_project_description", None) or "").strip()
            ),
            "PD run training": _float_cell(getattr(s, "tae_hours", None)),
            "Supervision": _float_cell(getattr(s, "supervision_hours", None)),
            "Total": f"{staff_tab_total_hours(s, snap):.2f}",
        }
        out.append(row)
    return out

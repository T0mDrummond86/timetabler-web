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
    "Hours owed",
    "Owed after cover",
)


def _float_cell(v: float | None) -> str:
    return "" if v is None else f"{float(v):g}"


def gather_staff_tab_main_rows(
    session: Session,
    *,
    timetable_session_id: int | None = None,
    ledger_by_name: dict[str, dict] | None = None,
) -> list[dict[str, str]]:
    """One dict per lecturer; keys match ``STAFF_TAB_EXPORT_HEADERS``.

    ``timetable_session_id`` scopes the export to one session's staff. It is
    optional so single-session (desktop) callers keep the all-staff behaviour;
    the multi-tenant web app must pass it, or the export leaks other sessions.

    ``ledger_by_name`` carries the cover ledger (hours owed, and what is left
    after logged cover), keyed by casefolded lecturer name. It is passed in
    rather than computed here because it depends on the global workspace, which
    only the web app has -- the desktop caller omits it and those two columns
    come out empty.
    """
    snap_map = staff_hours_snapshots_by_staff_id(session)
    out: list[dict[str, str]] = []
    query = session.query(Staff)
    if timetable_session_id is not None:
        query = query.filter(Staff.timetable_session_id == timetable_session_id)
    for s in query.order_by(Staff.name).all():
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
        led = (ledger_by_name or {}).get((s.name or "").strip().casefold()) or {}
        row["Hours owed"] = _float_cell(led.get("hours_owed"))
        row["Owed after cover"] = _float_cell(led.get("still_to_make_up"))
        out.append(row)
    return out

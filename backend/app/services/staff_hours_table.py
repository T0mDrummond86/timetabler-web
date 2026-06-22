"""Staff tab hours spreadsheet rows (desktop StaffEditor parity)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import Staff, StaffPreference
from timetable.core.staff_hours import (
    classify_staff_variance,
    lecturing_hours_from_fte,
    staff_hours_snapshot_for_bookings,
    staff_tab_total_hours,
)

from .global_staff_hours import staff_hours_snapshot_for_staff


def _prefs_text(prefs: dict[int, list[str]], priority: int) -> str:
    return ", ".join(prefs.get(priority, [])[:2])


def staff_hours_table_rows(db: Session, *, timetable_session_id: int) -> list[dict]:
    rows = (
        db.query(Staff)
        .filter(Staff.timetable_session_id == timetable_session_id)
        .order_by(Staff.name)
        .all()
    )
    if not rows:
        return []

    staff_ids = [s.id for s in rows]
    pref_rows = (
        db.query(StaffPreference)
        .filter(StaffPreference.staff_id.in_(staff_ids))
        .order_by(StaffPreference.staff_id, StaffPreference.priority, StaffPreference.slot_number)
        .all()
    )
    pref_by_staff: dict[int, dict[int, list[str]]] = {}
    for p in pref_rows:
        label = (p.class_name or p.qualification_name or "").strip()
        if not label:
            continue
        groups = pref_by_staff.setdefault(p.staff_id, {1: [], 2: [], 3: []})
        groups.setdefault(p.priority, []).append(label)

    out: list[dict] = []
    for s in rows:
        snap = staff_hours_snapshot_for_staff(db, s)
        lh = lecturing_hours_from_fte(s.fte)
        total = staff_tab_total_hours(s, snap)
        variance = (total - lh) if lh is not None else None
        category = (
            classify_staff_variance(fte=s.fte, lecturing_hours=lh, total_hours=total)
            if lh is not None
            else "unknown"
        )
        prefs = pref_by_staff.get(s.id, {1: [], 2: [], 3: []})
        out.append(
            {
                "id": s.id,
                "name": s.name,
                "staff_identifier": getattr(s, "staff_identifier", None),
                "cost_centre": getattr(s, "cost_centre", None),
                "fte": s.fte,
                "lecturing_hours": lh,
                "in_class_timetabled_hours": snap.regular_avg if snap else None,
                "session_schedule_avg": snap.session_schedule_breakdown if snap else None,
                "variance": variance,
                "variance_category": category,
                "bulk_online_detail": snap.online_breakdown if snap else None,
                "bulk_online_hours_avg": snap.online_avg if snap else None,
                "development_project_hours": getattr(s, "development_project_hours", None),
                "development_project_description": getattr(
                    s, "development_project_description", None
                ),
                "tae_hours": getattr(s, "tae_hours", None),
                "supervision_hours": getattr(s, "supervision_hours", None),
                "total_hours": total,
                "non_teaching_day": s.non_teaching_day,
                "preferences_first": _prefs_text(prefs, 1),
                "preferences_second": _prefs_text(prefs, 2),
                "preferences_third": _prefs_text(prefs, 3),
            }
        )
    return out

"""Extended staff detail payloads (hours, preferences, online students)."""
from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from timetable.core.booking_staff import staff_booking_filter_sql
from timetable.core.models import Booking, Staff, StaffPreference
from timetable.core.staff_hours import (
    classify_staff_variance,
    lecturing_hours_from_fte,
    staff_hours_snapshot_for_bookings,
    staff_hours_snapshots_by_staff_id,
    staff_tab_total_hours,
)


def staff_detail(db: Session, *, timetable_session_id: int, staff_id: int) -> dict:
    row = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.timetable_session_id == timetable_session_id)
        .first()
    )
    if row is None:
        raise LookupError("Staff not found")

    snap_map = staff_hours_snapshots_by_staff_id(db)
    snap = snap_map.get(staff_id)
    if snap is None:
        bookings = (
            db.query(Booking)
            .options(joinedload(Booking.room), joinedload(Booking.unit))
            .filter(staff_booking_filter_sql(staff_id, "all"))
            .all()
        )
        snap = staff_hours_snapshot_for_bookings(bookings, staff=row)

    prefs = (
        db.query(StaffPreference)
        .filter(StaffPreference.staff_id == staff_id)
        .order_by(StaffPreference.priority, StaffPreference.slot_number)
        .all()
    )
    pref_groups: dict[int, list[str]] = {1: [], 2: [], 3: []}
    for p in prefs:
        label = p.class_name or p.qualification_name or ""
        if label:
            pref_groups.setdefault(p.priority, []).append(label)

    from .staff_editor import online_student_rows_for_staff

    online_rows = online_student_rows_for_staff(db, staff_id)

    lh = lecturing_hours_from_fte(row.fte)
    total = staff_tab_total_hours(row, snap) if snap else None
    variance = (total - lh) if lh is not None and total is not None else None
    variance_category = (
        classify_staff_variance(
            fte=row.fte,
            lecturing_hours=lh,
            total_hours=total,
        )
        if total is not None
        else None
    )

    return {
        "id": row.id,
        "name": row.name,
        "fte": row.fte,
        "max_hours_per_week": row.max_hours_per_week,
        "non_teaching_day": row.non_teaching_day,
        "ot_hours": row.ot_hours,
        "development_project_hours": row.development_project_hours,
        "development_project_description": row.development_project_description,
        "tae_hours": row.tae_hours,
        "supervision_hours": row.supervision_hours,
        "default_online_students_per_class": row.default_online_students_per_class,
        "timetable_locked": row.timetable_locked or 0,
        "lecturing_hours": lh,
        "in_class_timetabled_hours": snap.regular_avg if snap else None,
        "session_schedule_avg": snap.session_schedule_breakdown if snap else None,
        "variance": variance,
        "variance_category": variance_category,
        "bulk_online_detail": snap.online_breakdown if snap else None,
        "bulk_online_hours_avg": snap.online_avg if snap else None,
        "total_hours": total,
        "preferences": {
            "first": pref_groups.get(1, []),
            "second": pref_groups.get(2, []),
            "third": pref_groups.get(3, []),
        },
        "online_students": online_rows,
    }

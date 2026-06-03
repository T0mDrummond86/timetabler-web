"""Class custodian report for a timetable session."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from timetable.core.models import Booking, Semester, Staff, Unit, Week


def class_custodians_for_session(db: Session, *, timetable_session_id: int) -> dict:
    units = (
        db.query(Unit)
        .filter(Unit.timetable_session_id == timetable_session_id)
        .order_by(Unit.name)
        .all()
    )
    week_ids = [
        int(wid)
        for (wid,) in db.query(Week.id)
        .join(Semester, Week.semester_id == Semester.id)
        .filter(Semester.timetable_session_id == timetable_session_id)
        .all()
    ]
    if not week_ids:
        return {"rows": [], "summary": "No timetable weeks in this session."}

    assigned = (
        db.query(Booking.unit_id, Booking.staff_id, func.count(Booking.id))
        .filter(
            Booking.week_id.in_(week_ids),
            Booking.unit_id.isnot(None),
            Booking.staff_id.isnot(None),
        )
        .group_by(Booking.unit_id, Booking.staff_id)
        .all()
    )
    unassigned = (
        db.query(Booking.unit_id, func.count(Booking.id))
        .filter(
            Booking.week_id.in_(week_ids),
            Booking.unit_id.isnot(None),
            Booking.staff_id.is_(None),
        )
        .group_by(Booking.unit_id)
        .all()
    )

    by_unit_staff: dict[int, dict[int, int]] = {}
    for uid, sid, n in assigned:
        by_unit_staff.setdefault(int(uid), {})[int(sid)] = int(n)
    unassigned_by_unit = {int(uid): int(n) for uid, n in unassigned}

    staff_ids: set[int] = set()
    for counts in by_unit_staff.values():
        staff_ids.update(counts.keys())
    staff_name: dict[int, str] = {}
    if staff_ids:
        for s in db.query(Staff).filter(Staff.id.in_(staff_ids)).all():
            staff_name[s.id] = s.name or f"#{s.id}"

    rows: list[dict] = []
    for u in units:
        counts = by_unit_staff.get(u.id, {})
        lecturers = sorted(
            [
                {"staff_id": sid, "name": staff_name.get(sid, f"#{sid}"), "deliveries": n}
                for sid, n in counts.items()
            ],
            key=lambda r: (-r["deliveries"], r["name"].lower(), r["staff_id"]),
        )
        custodian = lecturers[0] if lecturers else None
        unassigned_n = unassigned_by_unit.get(u.id, 0)
        lecturer_parts = [f"{d['name']} ({d['deliveries']})" for d in lecturers]
        if unassigned_n:
            lecturer_parts.append(f"Unassigned ({unassigned_n})")
        rows.append(
            {
                "unit_id": u.id,
                "unit_name": u.name or "(unnamed)",
                "lecturers": ", ".join(lecturer_parts) if lecturer_parts else "—",
                "custodian": custodian["name"] if custodian else "—",
                "custodian_deliveries": custodian["deliveries"] if custodian else 0,
                "unassigned_deliveries": unassigned_n,
            }
        )

    with_custodian = sum(1 for r in rows if r["custodian"] != "—")
    return {
        "rows": rows,
        "summary": f"{len(rows)} classes · {with_custodian} with an assigned custodian",
    }

"""Class custodian report for a timetable session."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from timetable.core.models import Booking, Qualification, Semester, Staff, Unit, UnitQualification, Week


def qualification_names_by_unit(db: Session, *, timetable_session_id: int) -> dict[int, str]:
    rows = (
        db.query(UnitQualification.unit_id, Qualification.name)
        .join(Qualification, UnitQualification.qualification_id == Qualification.id)
        .join(Unit, UnitQualification.unit_id == Unit.id)
        .filter(Unit.timetable_session_id == timetable_session_id)
        .order_by(Qualification.name)
        .all()
    )
    by_unit: dict[int, list[str]] = defaultdict(list)
    for uid, name in rows:
        by_unit[int(uid)].append((name or "").strip())
    return {uid: ", ".join(names) for uid, names in by_unit.items() if names}


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

    qual_by_unit = qualification_names_by_unit(db, timetable_session_id=timetable_session_id)

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
    # Overrides may name someone who never delivers the class, so their names
    # have to be fetched too or the column would read "#42".
    staff_ids.update(
        int(u.custodian_staff_id) for u in units if u.custodian_staff_id is not None
    )
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
        derived = lecturers[0] if lecturers else None

        # A hand-set custodian wins over the delivery count. It is dropped only
        # if the lecturer no longer exists in the session, which can happen
        # after a restore replaces the staff list.
        override_id = int(u.custodian_staff_id) if u.custodian_staff_id is not None else None
        override_name = staff_name.get(override_id) if override_id is not None else None
        if override_id is not None and override_name is None:
            override_id = None

        if override_id is not None:
            custodian_name = override_name or "—"
            custodian_id = override_id
            custodian_deliveries = counts.get(override_id, 0)
        else:
            custodian_name = derived["name"] if derived else "—"
            custodian_id = derived["staff_id"] if derived else None
            custodian_deliveries = derived["deliveries"] if derived else 0

        unassigned_n = unassigned_by_unit.get(u.id, 0)
        lecturer_parts = [f"{d['name']} ({d['deliveries']})" for d in lecturers]
        if unassigned_n:
            lecturer_parts.append(f"Unassigned ({unassigned_n})")
        rows.append(
            {
                "unit_id": u.id,
                "unit_name": u.name or "(unnamed)",
                # The component codes a class covers — labelled "Units" in the UI.
                "units": (u.component_codes or "").strip() or "—",
                "qualifications": qual_by_unit.get(u.id) or "—",
                "lecturers": ", ".join(lecturer_parts) if lecturer_parts else "—",
                "custodian": custodian_name,
                "custodian_staff_id": custodian_id,
                "custodian_deliveries": custodian_deliveries,
                "custodian_is_manual": override_id is not None,
                "unassigned_deliveries": unassigned_n,
                "candidates": [
                    {"staff_id": d["staff_id"], "name": d["name"], "deliveries": d["deliveries"]}
                    for d in lecturers
                ],
            }
        )

    with_custodian = sum(1 for r in rows if r["custodian"] != "—")
    return {
        "rows": rows,
        "summary": f"{len(rows)} classes · {with_custodian} with an assigned custodian",
    }

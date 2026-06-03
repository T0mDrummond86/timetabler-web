"""Staff editor save helpers (desktop StaffEditor parity)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import Staff, StaffPreference, StaffUnitOnlineStudents
from timetable.core.staff_hours import (
    DEFAULT_ONLINE_STUDENTS,
    load_unit_online_student_totals,
    online_student_targets_for_staff,
    resolve_unit_online_students,
)


def save_staff_preferences(
    db: Session,
    *,
    staff_id: int,
    first: list[str],
    second: list[str],
    third: list[str],
) -> None:
    db.query(StaffPreference).filter(StaffPreference.staff_id == staff_id).delete()
    for priority, names in ((1, first), (2, second), (3, third)):
        for slot_number, cname in enumerate(names[:2], start=1):
            db.add(
                StaffPreference(
                    staff_id=staff_id,
                    priority=priority,
                    slot_number=slot_number,
                    qualification_name=None,
                    class_name=cname.strip(),
                    unit_id=None,
                )
            )


def save_staff_unit_online_students(
    db: Session,
    *,
    staff_id: int,
    counts: list[dict],
) -> None:
    """``counts``: list of {unit_id, student_count} (null count = use default, delete override)."""
    staff = db.get(Staff, staff_id)
    if staff is None:
        raise LookupError("Staff not found")

    targets = {t.unit_id: t for t in online_student_targets_for_staff(db, staff_id)}
    unit_stored = load_unit_online_student_totals(db, staff_id)

    for item in counts:
        unit_id = int(item["unit_id"])
        if unit_id not in targets:
            continue
        target = targets[unit_id]
        default_total = resolve_unit_online_students(
            unit_id, target.session_count, unit_stored
        )
        raw = item.get("student_count")
        row = (
            db.query(StaffUnitOnlineStudents)
            .filter_by(staff_id=staff_id, unit_id=unit_id)
            .one_or_none()
        )
        if raw is None or int(raw) == default_total:
            if row is not None:
                db.delete(row)
            continue
        if row is None:
            row = StaffUnitOnlineStudents(staff_id=staff_id, unit_id=unit_id)
            db.add(row)
        row.student_count = int(raw)


def online_student_rows_for_staff(db: Session, staff_id: int) -> list[dict]:
    """Editable online-student targets with resolved default counts."""
    unit_stored = load_unit_online_student_totals(db, staff_id)
    rows: list[dict] = []
    for target in online_student_targets_for_staff(db, staff_id):
        default_count = resolve_unit_online_students(
            target.unit_id, target.session_count, unit_stored
        )
        stored = unit_stored.get(target.unit_id)
        rows.append(
            {
                "unit_id": target.unit_id,
                "label": target.label,
                "session_count": target.session_count,
                "default_count": default_count,
                "student_count": stored if stored is not None else default_count,
            }
        )
    return rows

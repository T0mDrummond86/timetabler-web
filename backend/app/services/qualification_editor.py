"""Qualification editor helpers (desktop QualificationEditor parity)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.block_delivery import (
    block_delivery_summary,
    block_qualification_group_courses,
    is_block_qualification,
    qualification_group_code,
    regular_qualification_group_courses,
)
from timetable.core.models import Booking, Course, Qualification, Unit, UnitQualification
from timetable.core.qualification_schedule import schedule_period_summary


def qualification_detail(
    db: Session,
    *,
    timetable_session_id: int,
    qualification_id: int,
) -> dict:
    q = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == timetable_session_id,
        )
        .first()
    )
    if q is None:
        raise LookupError("Qualification not found")

    regular = regular_qualification_group_courses(db, q)
    block = block_qualification_group_courses(db, q) if is_block_qualification(q) else []

    if is_block_qualification(q):
        if block:
            block_status = (
                f"{block_delivery_summary(q)}. "
                "Set block length and start week in the Block delivery timetable view."
            )
        else:
            block_status = "No block groups yet. Click Create block to add a block cohort."
    else:
        block_status = (
            "Regular semester delivery. Use Create block for an intensive block timetable."
        )

    summary_parts: list[str] = []
    if regular:
        summary_parts.append("Regular groups: " + ", ".join(c.code for c in regular))
    elif not is_block_qualification(q):
        summary_parts.append("No group courses yet — saving will create them.")
    if block:
        summary_parts.append("Block groups: " + ", ".join(c.code for c in block))

    linked = (
        db.query(Unit)
        .join(UnitQualification, UnitQualification.unit_id == Unit.id)
        .filter(UnitQualification.qualification_id == qualification_id)
        .order_by(Unit.name)
        .all()
    )

    return {
        "id": q.id,
        "name": q.name,
        "num_groups": max(max(1, getattr(q, "num_groups", 1) or 1), len(regular)),
        "schedule_period": getattr(q, "schedule_period", None) or "day",
        "delivery_mode": getattr(q, "delivery_mode", None) or "regular",
        "groups_summary": " ".join(summary_parts),
        "schedule_summary": schedule_period_summary(getattr(q, "schedule_period", None)),
        "block_status": block_status,
        "regular_groups": [{"id": c.id, "code": c.code} for c in regular],
        "block_groups": [{"id": c.id, "code": c.code} for c in block],
        "linked_classes": [{"id": u.id, "name": u.name} for u in linked],
    }


def sync_qualification_regular_groups(db: Session, qual: Qualification, new_count: int) -> None:
    """Create or remove regular (non-block) cohort courses when num_groups changes."""
    new_count = max(1, int(new_count))
    qual.num_groups = new_count
    existing = (
        db.query(Course)
        .filter_by(qualification_id=qual.id, is_block_cohort=0)
        .order_by(Course.code)
        .all()
    )
    existing_count = len(existing)
    if new_count > existing_count:
        for i in range(existing_count, new_count):
            code = qualification_group_code(qual.name, i)
            existing_by_code = (
                db.query(Course)
                .filter_by(code=code, timetable_session_id=qual.timetable_session_id)
                .first()
            )
            if existing_by_code is not None:
                if existing_by_code.is_block_cohort:
                    continue
                if existing_by_code.qualification_id != qual.id:
                    existing_by_code.qualification_id = qual.id
                continue
            db.add(
                Course(
                    code=code,
                    qualification_id=qual.id,
                    is_block_cohort=0,
                    timetable_session_id=qual.timetable_session_id,
                )
            )
    elif new_count < existing_count:
        surplus = existing[new_count:]
        booking_count = (
            db.query(Booking)
            .filter(Booking.course_id.in_([c.id for c in surplus]))
            .count()
            if surplus
            else 0
        )
        if booking_count:
            raise ValueError(
                f"Cannot reduce to {new_count} group(s): {booking_count} booking(s) "
                f"still use {len(surplus)} group course(s). Remove or move those bookings first."
            )
        for course in surplus:
            db.delete(course)

"""Create/delete session entities and unit↔qualification links."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import Qualification, Room, Staff, Unit, UnitQualification
from timetable.core.qualification_schedule import replace_qualification_time_windows
from timetable.core.sidebar_order import next_staff_sidebar_order
from timetable.core.staff_bookings import clear_lecturer_from_bookings


def create_staff(db: Session, *, timetable_session_id: int, name: str) -> Staff:
    name = name.strip()
    if not name:
        raise ValueError("Name is required")
    row = Staff(
        name=name,
        timetable_session_id=timetable_session_id,
        sidebar_order=next_staff_sidebar_order(db),
    )
    db.add(row)
    db.flush()
    return row


def delete_staff(db: Session, *, timetable_session_id: int, staff_id: int) -> dict:
    row = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.timetable_session_id == timetable_session_id)
        .first()
    )
    if row is None:
        raise LookupError("Staff not found")
    cleared = clear_lecturer_from_bookings(db, staff_id)
    name = row.name
    db.delete(row)
    db.flush()
    return {"name": name, "bookings_cleared": cleared}


def create_room(db: Session, *, timetable_session_id: int, code: str) -> Room:
    code = code.strip()
    if not code:
        raise ValueError("Room code is required")
    row = Room(code=code, timetable_session_id=timetable_session_id)
    db.add(row)
    db.flush()
    return row


def delete_room(db: Session, *, timetable_session_id: int, room_id: int) -> str:
    row = (
        db.query(Room)
        .filter(Room.id == room_id, Room.timetable_session_id == timetable_session_id)
        .first()
    )
    if row is None:
        raise LookupError("Room not found")
    code = row.code
    db.delete(row)
    db.flush()
    return code


def create_unit(db: Session, *, timetable_session_id: int, name: str) -> Unit:
    name = name.strip()
    if not name:
        raise ValueError("Name is required")
    row = Unit(name=name, timetable_session_id=timetable_session_id)
    db.add(row)
    db.flush()
    return row


def delete_unit(db: Session, *, timetable_session_id: int, unit_id: int) -> str:
    row = (
        db.query(Unit)
        .filter(Unit.id == unit_id, Unit.timetable_session_id == timetable_session_id)
        .first()
    )
    if row is None:
        raise LookupError("Unit not found")
    name = row.name
    db.delete(row)
    db.flush()
    return name


def create_qualification(
    db: Session,
    *,
    timetable_session_id: int,
    name: str,
    schedule_period: str = "day",
) -> Qualification:
    name = name.strip()
    if not name:
        raise ValueError("Name is required")
    row = Qualification(
        name=name,
        timetable_session_id=timetable_session_id,
        schedule_period=schedule_period,
    )
    db.add(row)
    db.flush()
    replace_qualification_time_windows(db, row)
    db.flush()
    return row


def delete_qualification(
    db: Session,
    *,
    timetable_session_id: int,
    qualification_id: int,
) -> str:
    row = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == timetable_session_id,
        )
        .first()
    )
    if row is None:
        raise LookupError("Qualification not found")
    name = row.name
    db.delete(row)
    db.flush()
    return name


def set_unit_qualifications(
    db: Session,
    *,
    timetable_session_id: int,
    unit_id: int,
    qualification_ids: list[int],
) -> list[int]:
    unit = (
        db.query(Unit)
        .filter(Unit.id == unit_id, Unit.timetable_session_id == timetable_session_id)
        .first()
    )
    if unit is None:
        raise LookupError("Unit not found")
    valid_ids = {
        q.id
        for q in db.query(Qualification)
        .filter(
            Qualification.timetable_session_id == timetable_session_id,
            Qualification.id.in_(qualification_ids or [-1]),
        )
        .all()
    }
    db.query(UnitQualification).filter(UnitQualification.unit_id == unit_id).delete()
    for qid in qualification_ids:
        if qid in valid_ids:
            db.add(UnitQualification(unit_id=unit_id, qualification_id=qid))
    db.flush()
    return sorted(valid_ids.intersection(qualification_ids))


def unit_qualification_ids(db: Session, unit_id: int) -> list[int]:
    return [
        int(row[0])
        for row in db.query(UnitQualification.qualification_id)
        .filter(UnitQualification.unit_id == unit_id)
        .order_by(UnitQualification.qualification_id)
        .all()
    ]


def unit_to_out(db: Session, unit: Unit) -> dict:
    return {
        "id": unit.id,
        "name": unit.name,
        "length_slots": unit.length_slots,
        "component_codes": unit.component_codes,
        "double_session": getattr(unit, "double_session", 0) or 0,
        "double_session_same_day": getattr(unit, "double_session_same_day", None),
        "double_session_first_slots": getattr(unit, "double_session_first_slots", None),
        "screen_fill_colour": getattr(unit, "screen_fill_colour", None),
        "qualification_ids": unit_qualification_ids(db, unit.id),
    }

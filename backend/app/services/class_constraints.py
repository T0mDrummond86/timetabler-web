"""Staff competency and unit allowed-room links."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import Room, Staff, StaffCompetency, Unit, UnitAllowedRoom


def unit_allowed_room_ids(db: Session, unit_id: int) -> list[int]:
    return [
        int(row[0])
        for row in db.query(UnitAllowedRoom.room_id)
        .filter(UnitAllowedRoom.unit_id == unit_id)
        .order_by(UnitAllowedRoom.room_id)
        .all()
    ]


def staff_competency_unit_ids(db: Session, staff_id: int) -> list[int]:
    return [
        int(row[0])
        for row in db.query(StaffCompetency.unit_id)
        .filter(StaffCompetency.staff_id == staff_id)
        .order_by(StaffCompetency.unit_id)
        .all()
    ]


def set_unit_allowed_rooms(
    db: Session,
    *,
    timetable_session_id: int,
    unit_id: int,
    room_ids: list[int],
) -> list[int]:
    unit = (
        db.query(Unit)
        .filter(Unit.id == unit_id, Unit.timetable_session_id == timetable_session_id)
        .first()
    )
    if unit is None:
        raise LookupError("Unit not found")
    valid = {
        r.id
        for r in db.query(Room)
        .filter(
            Room.timetable_session_id == timetable_session_id,
            Room.id.in_(room_ids or [-1]),
        )
        .all()
    }
    db.query(UnitAllowedRoom).filter(UnitAllowedRoom.unit_id == unit_id).delete()
    for rid in room_ids:
        if rid in valid:
            db.add(UnitAllowedRoom(unit_id=unit_id, room_id=rid))
    db.flush()
    return sorted(valid.intersection(room_ids))


def set_unit_competencies(
    db: Session,
    *,
    timetable_session_id: int,
    unit_id: int,
    staff_ids: list[int],
) -> list[int]:
    unit = (
        db.query(Unit)
        .filter(Unit.id == unit_id, Unit.timetable_session_id == timetable_session_id)
        .first()
    )
    if unit is None:
        raise LookupError("Unit not found")
    valid = {
        s.id
        for s in db.query(Staff)
        .filter(
            Staff.timetable_session_id == timetable_session_id,
            Staff.id.in_(staff_ids or [-1]),
        )
        .all()
    }
    db.query(StaffCompetency).filter(StaffCompetency.unit_id == unit_id).delete()
    for sid in staff_ids:
        if sid in valid:
            db.add(StaffCompetency(staff_id=sid, unit_id=unit_id))
    db.flush()
    return sorted(valid.intersection(staff_ids))


def set_staff_competencies(
    db: Session,
    *,
    timetable_session_id: int,
    staff_id: int,
    unit_ids: list[int],
) -> list[int]:
    staff = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.timetable_session_id == timetable_session_id)
        .first()
    )
    if staff is None:
        raise LookupError("Staff not found")
    valid = {
        u.id
        for u in db.query(Unit)
        .filter(
            Unit.timetable_session_id == timetable_session_id,
            Unit.id.in_(unit_ids or [-1]),
        )
        .all()
    }
    db.query(StaffCompetency).filter(StaffCompetency.staff_id == staff_id).delete()
    for uid in unit_ids:
        if uid in valid:
            db.add(StaffCompetency(staff_id=staff_id, unit_id=uid))
    db.flush()
    return sorted(valid.intersection(unit_ids))

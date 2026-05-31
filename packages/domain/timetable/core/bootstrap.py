"""Bootstrap constraint data from observed bookings.

Run after import_overall() to seed:
- StaffCompetency: any (staff, unit) pair that's been seen in a booking.
- Room.capacity: default 24 (typical TAFE classroom) where unset.
- Room.room_type: 'online' for known online rooms (e.g. 'Collaborate'),
  otherwise 'on-campus' if unset.
- Staff.max_hours_per_week: 30 (rough default) where unset.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .models import Booking, Room, Staff, StaffCompetency, Unit
from .room_types import infer_room_type_from_room
DEFAULT_ROOM_CAPACITY = 24
DEFAULT_STAFF_CAP = 30.0


@dataclass
class BootstrapReport:
    competencies_added: int = 0
    rooms_typed: int = 0
    rooms_capacity_set: int = 0
    staff_caps_set: int = 0


def bootstrap(session: Session) -> BootstrapReport:
    rep = BootstrapReport()

    # --- 1. Competencies inferred from observed (staff, unit) pairs ---
    seen: set[tuple[int, int]] = set(
        session.query(Booking.staff_id, Booking.unit_id)
        .filter(Booking.staff_id.isnot(None), Booking.unit_id.isnot(None))
        .distinct()
        .all()
    )
    existing: set[tuple[int, int]] = set(
        session.query(StaffCompetency.staff_id, StaffCompetency.unit_id).all()
    )
    for pair in seen - existing:
        session.add(StaffCompetency(staff_id=pair[0], unit_id=pair[1]))
        rep.competencies_added += 1

    # --- 2. Room types + capacity defaults ---
    for r in session.query(Room).all():
        if r.room_type is None:
            r.room_type = infer_room_type_from_room(r)
            rep.rooms_typed += 1
        if r.capacity is None:
            r.capacity = DEFAULT_ROOM_CAPACITY
            rep.rooms_capacity_set += 1

    # --- 3. Staff weekly hour caps ---
    for s in session.query(Staff).all():
        if s.max_hours_per_week is None:
            s.max_hours_per_week = DEFAULT_STAFF_CAP
            rep.staff_caps_set += 1

    session.commit()
    return rep

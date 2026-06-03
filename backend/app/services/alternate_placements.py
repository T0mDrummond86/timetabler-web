"""Valid alternate day/time/room placements for a booking."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.constants import DAYS
from timetable.core.alternate_slots import (
    AlternatePlacement,
    alternate_placements_by_day,
    available_rooms_at_current_slot,
)
from timetable.core.models import Booking, Room

from .timetable_grid import get_repeating_week


def _room_code(db: Session, room_id: int | None) -> str | None:
    if room_id is None:
        return None
    room = db.get(Room, room_id)
    return room.code if room else f"#{room_id}"


def alternate_slots_for_booking(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
    times_only: bool = False,
    fixed_room_id: int | None = None,
) -> dict:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return {"days": [], "available_rooms": []}

    booking = db.get(Booking, booking_id)
    if booking is None or booking.week_id != week.id:
        raise ValueError("Booking not found")

    week_bookings = db.query(Booking).filter(Booking.week_id == week.id).all()
    lock_staff = bool(getattr(booking, "lock_staff", 0))

    by_day = alternate_placements_by_day(
        db,
        booking,
        week_bookings,
        times_only=times_only,
        fixed_room_id=fixed_room_id,
        lock_staff=lock_staff,
    )

    days_out: list[dict] = []
    for day_idx in sorted(by_day):
        placements = by_day[day_idx]
        grouped: dict[int, list[AlternatePlacement]] = {}
        for p in placements:
            grouped.setdefault(p.start_slot, []).append(p)

        slot_rows: list[dict] = []
        for start in sorted(grouped):
            group = grouped[start]
            options = []
            for p in group:
                is_current = (
                    p.day == booking.day
                    and p.start_slot == booking.start_slot
                    and p.room_id == booking.room_id
                )
                room_code = _room_code(db, p.room_id) or "—"
                options.append(
                    {
                        "day": p.day,
                        "start_slot": p.start_slot,
                        "end_slot": p.end_slot,
                        "time_label": p.time_label,
                        "room_id": p.room_id,
                        "room_code": room_code,
                        "staff_id": p.staff_id,
                        "is_current": is_current,
                    }
                )
            slot_rows.append(
                {
                    "start_slot": start,
                    "time_label": group[0].time_label,
                    "options": options,
                }
            )

        days_out.append(
            {
                "day": day_idx,
                "day_label": DAYS[day_idx],
                "is_current_day": day_idx == booking.day,
                "slots": slot_rows,
            }
        )

    room_ids = available_rooms_at_current_slot(db, booking, week_bookings)
    available_rooms = [
        {
            "room_id": rid,
            "room_code": _room_code(db, rid) or f"#{rid}",
            "is_current": rid == booking.room_id,
        }
        for rid in room_ids
    ]

    return {"days": days_out, "available_rooms": available_rooms}

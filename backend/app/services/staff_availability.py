"""Staff blocked-slot grid (inverse of availability windows)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.constants import NUM_DAYS, NUM_SLOTS
from timetable.core.models import Staff, StaffAvailability


def _windows_from_blocked(blocked: set[tuple[int, int]]) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    for day in range(NUM_DAYS):
        slot = 0
        while slot < NUM_SLOTS:
            while slot < NUM_SLOTS and (day, slot) in blocked:
                slot += 1
            if slot >= NUM_SLOTS:
                break
            end = slot
            while end < NUM_SLOTS and (day, end) not in blocked:
                end += 1
            out.append((day, slot, end))
            slot = end
    return out


def blocked_slots_for_staff(db: Session, *, staff_id: int) -> list[dict]:
    staff = db.get(Staff, staff_id)
    if staff is None:
        raise ValueError("Staff not found")

    windows = db.query(StaffAvailability).filter(StaffAvailability.staff_id == staff_id).all()
    if not windows:
        return []

    available: set[tuple[int, int]] = set()
    for w in windows:
        if not (0 <= w.day < NUM_DAYS):
            continue
        for s in range(max(0, w.start_slot), min(NUM_SLOTS, w.end_slot)):
            available.add((w.day, s))

    blocked: list[dict] = []
    for day in range(NUM_DAYS):
        for slot in range(NUM_SLOTS):
            if (day, slot) not in available:
                blocked.append({"day": day, "slot": slot})
    return blocked


def set_blocked_slots_for_staff(
    db: Session,
    *,
    staff_id: int,
    blocked: list[tuple[int, int]],
) -> None:
    staff = db.get(Staff, staff_id)
    if staff is None:
        raise ValueError("Staff not found")

    blocked_set = {(int(d), int(s)) for d, s in blocked}
    db.query(StaffAvailability).filter(StaffAvailability.staff_id == staff_id).delete()
    if blocked_set:
        for day, start, end in _windows_from_blocked(blocked_set):
            if end > start:
                db.add(
                    StaffAvailability(
                        staff_id=staff_id,
                        day=day,
                        start_slot=start,
                        end_slot=end,
                    )
                )

"""Staff and room usage matrices (desktop UsageWindow)."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session, joinedload

from timetable.constants import DAYS, NUM_DAYS, NUM_SLOTS, slot_to_time
from timetable.core.class_colour import booking_colour_key
from timetable.core.models import Booking, Room, Staff, Week
from timetable.core.room_types import room_is_physical

from ..colours import class_colours

from .timetable_grid import get_repeating_week


def _staff_initials(staff: Staff) -> str:
    parts = [p for p in (staff.name or "").split() if p]
    if not parts:
        return "?"
    return "".join(p[0].upper() for p in parts[:3])


def _staff_column_labels(staff_list: list[Staff]) -> list[str]:
    """Column headers: initials, disambiguated when duplicates (e.g. two 'TD')."""
    from collections import Counter

    initials_counts = Counter(_staff_initials(s) for s in staff_list)
    labels: list[str] = []
    for s in staff_list:
        ini = _staff_initials(s)
        if initials_counts[ini] <= 1:
            labels.append(ini)
            continue
        parts = (s.name or "").strip().split()
        if len(parts) >= 2:
            labels.append(f"{parts[0][0]}{parts[-1][0:2]}".upper())
        else:
            labels.append(f"{ini}{s.id % 10}")
    return labels


def _term_label(booking: Booking) -> str:
    t1 = bool(getattr(booking, "in_term_1", 1))
    t2 = bool(getattr(booking, "in_term_2", 1))
    if t1 and t2:
        return ""
    if t1:
        return "T1"
    if t2:
        return "T2"
    return ""


def _tooltip(booking: Booking) -> str:
    end = (
        slot_to_time(booking.end_slot).strftime("%H:%M")
        if booking.end_slot < NUM_SLOTS
        else "22:00"
    )
    return (
        f"Course: {booking.course.code if booking.course else '—'}\n"
        f"Class: {booking.unit.name if booking.unit else '—'}\n"
        f"Staff: {booking.staff.name if booking.staff else '—'}\n"
        f"Room: {booking.room.code if booking.room else '—'}\n"
        f"Time: {DAYS[booking.day]} {slot_to_time(booking.start_slot).strftime('%H:%M')}–{end}"
    )


def _build_usage(
    db: Session,
    *,
    timetable_session_id: int,
    kind: str,
) -> dict:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return {
            "kind": kind,
            "resources": [],
            "resource_ids": [],
            "resource_tooltips": [],
            "days": list(DAYS),
            "num_slots": NUM_SLOTS,
            "cells": [],
            "summary": "No timetable week",
        }

    if kind == "staff":
        resources = (
            db.query(Staff)
            .filter(Staff.timetable_session_id == timetable_session_id)
            .order_by(Staff.name)
            .all()
        )
        labels = _staff_column_labels(resources)
        tooltips = [r.name or f"Staff #{r.id}" for r in resources]
        attr = "staff_id"
    else:
        resources = [
            r
            for r in db.query(Room)
            .filter(Room.timetable_session_id == timetable_session_id)
            .order_by(Room.code)
            .all()
            if room_is_physical(r)
        ]
        labels = [r.code for r in resources]
        tooltips = [r.name or r.code for r in resources]
        attr = "room_id"

    bookings = (
        db.query(Booking)
        .options(
            joinedload(Booking.course),
            joinedload(Booking.unit),
            joinedload(Booking.staff),
            joinedload(Booking.room),
        )
        .filter(Booking.week_id == week.id)
        .all()
    )

    res_col = {r.id: i for i, r in enumerate(resources)}
    cell_load: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for b in bookings:
        res_id = getattr(b, attr)
        if res_id is None or res_id not in res_col:
            continue
        for s in range(b.start_slot, b.end_slot):
            cell_load[(res_id, b.day, s)].append(b.id)

    clashing: set[int] = set()
    for bids in cell_load.values():
        if len(bids) > 1:
            clashing.update(bids)

    # cells[day][slot][resource_index]
    cells: list[list[list[dict]]] = []
    for day in range(NUM_DAYS):
        day_rows: list[list[dict]] = []
        for slot in range(NUM_SLOTS):
            row: list[dict] = []
            for res_idx, res in enumerate(resources):
                matching = [
                    b
                    for b in bookings
                    if getattr(b, attr) == res.id
                    and b.day == day
                    and b.start_slot <= slot < b.end_slot
                ]
                if not matching:
                    row.append(
                        {
                            "booking_id": None,
                            "label": "",
                            "fill_colour": "",
                            "status": "free",
                            "tooltip": "",
                        }
                    )
                    continue
                # Prefer booking that starts at this slot for label
                main = next((b for b in matching if b.start_slot == slot), matching[0])
                group = [
                    b
                    for b in bookings
                    if getattr(b, attr) == res.id
                    and b.day == day
                    and b.start_slot == main.start_slot
                    and b.end_slot == main.end_slot
                ]
                t1 = next(
                    (b for b in group if getattr(b, "in_term_1", 1) and not getattr(b, "in_term_2", 1)),
                    None,
                )
                t2 = next(
                    (b for b in group if getattr(b, "in_term_2", 1) and not getattr(b, "in_term_1", 1)),
                    None,
                )
                if len(group) == 2 and t1 and t2:
                    label = "T1·T2"
                    paint = t1
                else:
                    paint = group[0]
                    label = _term_label(paint) or (paint.course.code if paint.course else "")
                clash = any(b.id in clashing for b in group)
                fill, _ = class_colours(booking_colour_key(paint, by_class=True))
                row.append(
                    {
                        "booking_id": paint.id,
                        "label": label if slot == paint.start_slot else "",
                        "fill_colour": fill,
                        "status": "clash" if clash else "busy",
                        "tooltip": "\n\n".join(_tooltip(b) for b in group) if slot == paint.start_slot else "",
                        "row_span": paint.end_slot - paint.start_slot if slot == paint.start_slot else 0,
                    }
                )
            day_rows.append(row)
        cells.append(day_rows)

    n_clash = len(clashing)
    kind_word = "lecturers" if kind == "staff" else "rooms"
    return {
        "kind": kind,
        "resources": labels,
        "resource_ids": [r.id for r in resources],
        "resource_tooltips": tooltips,
        "days": list(DAYS),
        "num_slots": NUM_SLOTS,
        "cells": cells,
        "summary": f"{len(resources)} {kind_word} · {len(bookings)} bookings · {n_clash} bookings in clashes",
    }


def staff_usage(db: Session, *, timetable_session_id: int) -> dict:
    return _build_usage(db, timetable_session_id=timetable_session_id, kind="staff")


def room_usage(db: Session, *, timetable_session_id: int) -> dict:
    return _build_usage(db, timetable_session_id=timetable_session_id, kind="room")

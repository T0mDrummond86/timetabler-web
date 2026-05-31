"""Hard constraints linking the two bookings of a double-session class."""
from __future__ import annotations

from collections import defaultdict

from ortools.sat.python import cp_model

from ..core.double_session import double_session_same_day, unit_has_double_session
from ..core.scheduling_constraints import MIN_BREAK_SLOTS


def double_session_booking_pairs(bookings: list, unit_all: dict) -> list[tuple]:
    """Return (part_1_booking, part_2_booking) for each double-session (course, unit)."""
    by_key: dict[tuple[int, int], dict[int, object]] = defaultdict(dict)
    for b in bookings:
        if b.course_id is None or b.unit_id is None:
            continue
        unit = unit_all.get(b.unit_id)
        if not unit_has_double_session(unit):
            continue
        part = getattr(b, "session_part", 1) or 1
        by_key[(b.course_id, b.unit_id)][part] = b
    pairs: list[tuple] = []
    for parts in by_key.values():
        if 1 in parts and 2 in parts:
            pairs.append((parts[1], parts[2]))
    return pairs


def _duration(b, durations: dict[int, int]) -> int:
    return durations.get(b.id, b.end_slot - b.start_slot)


def _choice_value(entity_id: int | None) -> int:
    return -1 if entity_id is None else entity_id


def _link_staff_room(
    model: cp_model.CpModel,
    *,
    staff_choice: dict[int, cp_model.IntVar],
    room_choice: dict[int, cp_model.IntVar],
    b_mov,
    b_fix,
) -> None:
    model.Add(staff_choice[b_mov.id] == _choice_value(b_fix.staff_id))
    model.Add(room_choice[b_mov.id] == _choice_value(b_fix.room_id))


def _link_same_day_timing(
    model: cp_model.CpModel,
    *,
    b1,
    b2,
    durations: dict[int, int],
    day_var: dict[int, cp_model.IntVar],
    start_var: dict[int, cp_model.IntVar],
) -> None:
    """Session 2 starts 30 minutes after session 1 ends (part 1 = b1, part 2 = b2)."""
    dur1 = _duration(b1, durations)
    m1 = b1.id in start_var
    m2 = b2.id in start_var
    if m1 and m2:
        model.Add(day_var[b1.id] == day_var[b2.id])
        model.Add(start_var[b2.id] == start_var[b1.id] + dur1 + MIN_BREAK_SLOTS)
    elif m1 and not m2:
        model.Add(day_var[b1.id] == b2.day)
        model.Add(b2.start_slot == start_var[b1.id] + dur1 + MIN_BREAK_SLOTS)
    elif not m1 and m2:
        model.Add(day_var[b2.id] == b1.day)
        model.Add(start_var[b2.id] == b1.start_slot + dur1 + MIN_BREAK_SLOTS)
    # both fixed: nothing to constrain in the model


def _link_different_days(
    model: cp_model.CpModel,
    *,
    b1,
    b2,
    day_var: dict[int, cp_model.IntVar],
) -> None:
    m1 = b1.id in day_var
    m2 = b2.id in day_var
    if m1 and m2:
        model.Add(day_var[b1.id] != day_var[b2.id])
    elif m1 and not m2:
        model.Add(day_var[b1.id] != b2.day)
    elif not m1 and m2:
        model.Add(day_var[b2.id] != b1.day)


def add_double_session_constraints(
    model: cp_model.CpModel,
    *,
    bookings: list,
    unit_all: dict,
    staff_choice: dict[int, cp_model.IntVar],
    room_choice: dict[int, cp_model.IntVar],
    day_var: dict[int, cp_model.IntVar],
    start_var: dict[int, cp_model.IntVar],
    durations: dict[int, int],
) -> None:
    """Same lecturer & room; same-day pairs also share day with a 30-minute gap."""
    for b1, b2 in double_session_booking_pairs(bookings, unit_all):
        unit = unit_all.get(b1.unit_id)
        if unit is None:
            continue
        m1 = b1.id in staff_choice
        m2 = b2.id in staff_choice
        if not m1 and not m2:
            continue
        if m1 and m2:
            model.Add(staff_choice[b1.id] == staff_choice[b2.id])
            model.Add(room_choice[b1.id] == room_choice[b2.id])
        elif m1:
            _link_staff_room(
                model, staff_choice=staff_choice, room_choice=room_choice, b_mov=b1, b_fix=b2
            )
        else:
            _link_staff_room(
                model, staff_choice=staff_choice, room_choice=room_choice, b_mov=b2, b_fix=b1
            )
        if double_session_same_day(unit):
            _link_same_day_timing(
                model,
                b1=b1,
                b2=b2,
                durations=durations,
                day_var=day_var,
                start_var=start_var,
            )
        else:
            _link_different_days(model, b1=b1, b2=b2, day_var=day_var)

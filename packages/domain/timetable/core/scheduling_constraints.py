"""Timetable-wide scheduling constraints (auto-timetabler + validation)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import time
from typing import Iterable

from ..constants import DAYS, NUM_DAYS, NUM_SLOTS, SLOT_MINUTES, time_to_slot
from .models import Booking

# --- Time limits (30-minute slot grid from 08:00) ---
MONDAY = 0
FRIDAY = NUM_DAYS - 1
MONDAY_MIN_START_SLOT = time_to_slot(time(9, 30))
FRIDAY_MAX_END_SLOT = time_to_slot(time(18, 0))
from .continuous_teaching_break import (
    MIN_BREAK_SLOTS,
    SIX_HOUR_SLOT_WINDOW,
    continuous_6h_teaching_violated,
    group_sessions_into_blocks,
    iter_continuous_6h_violation_blocks,
    staff_day_sessions,
)
MAX_IDLE_GAP_SLOTS = 4  # 2 hours
MIN_DAILY_TEACHING_SLOTS = 10  # 5 hours (staff + student floor on teaching days)
MAX_DAILY_TEACHING_SLOTS = 18  # 9 hours (staff ceiling on teaching days)
STUDENT_IDEAL_MIN_DAILY_TEACHING_SLOTS = 10  # 5 hours
STUDENT_IDEAL_MAX_DAILY_TEACHING_SLOTS = 16  # 8 hours — auto-solve sweet spot
STUDENT_MAX_IDLE_GAP_SLOTS = 4  # 2 hours between cohort classes

# Objective weights (medium > weak; drift is typically 0–~140 per booking).
PENALTY_MONDAY_EARLY_START = 120
PENALTY_STUDENT_DAILY_HOURS = 90
PENALTY_STUDENT_LONG_IDLE = 70
PENALTY_LONG_IDLE_GAP = 40
PENALTY_STAFF_DAILY_HOURS = 30

FRIDAY_LABEL = DAYS[FRIDAY]


@dataclass
class SchedulingConstraintSettings:
    """Timetable placement rules (auto-timetable tab toggles)."""

    # Strong — must hold
    break_every_6_hours: bool = True
    friday_finish_by_6pm: bool = True
    # Medium — ideal
    monday_start_after_930: bool = True
    student_daily_hours_5_to_9: bool = True
    student_break_max_2_hours: bool = True
    # Weak — ideal, lower priority than medium
    max_idle_gap_2_hours: bool = True
    staff_daily_hours_5_to_9: bool = True


def filter_day_start_pairs(
    pairs: list[tuple[int, int]],
    duration_slots: int,
    settings: SchedulingConstraintSettings,
) -> list[tuple[int, int]]:
    """Remove placements that violate strong scheduling rules."""
    if not settings.friday_finish_by_6pm:
        return pairs
    out: list[tuple[int, int]] = []
    for day, start in pairs:
        if day == FRIDAY and start + duration_slots > FRIDAY_MAX_END_SLOT:
            continue
        out.append((day, start))
    return out


def fixed_occupied_slots_by_staff_day(
    fixed: list[Booking],
) -> dict[tuple[int, int], set[int]]:
    """``(staff_id, day)`` → set of occupied slot indices from fixed bookings."""
    occ: dict[tuple[int, int], set[int]] = defaultdict(set)
    for b in fixed:
        if b.staff_id is None:
            continue
        for t in range(b.start_slot, b.end_slot):
            if 0 <= b.day < NUM_DAYS and 0 <= t < NUM_SLOTS:
                occ[(b.staff_id, b.day)].add(t)
    return occ


def placement_violates_6h_break(
    staff_id: int,
    day: int,
    start: int,
    duration_slots: int,
    occupied: dict[tuple[int, int], set[int]] | None = None,
    *,
    fixed: list[Booking] | None = None,
) -> bool:
    """True if placing this session breaks the continuous 6-hour teaching rule."""
    if fixed is not None:
        sessions = staff_day_sessions(
            fixed,
            staff_id,
            day,
            extra_start=start,
            extra_duration=duration_slots,
        )
        return continuous_6h_teaching_violated(sessions)
    # Legacy slot-set callers (avoid if possible).
    del occupied
    sessions = [(start, start + duration_slots)]
    return continuous_6h_teaching_violated(sessions)


def _slots_for_bookings(day_bookings: list[Booking]) -> set[int]:
    slots: set[int] = set()
    for b in day_bookings:
        for t in range(b.start_slot, b.end_slot):
            slots.add(t)
    return slots


def _hours_from_slots(slots: set[int]) -> float:
    return len(slots) * SLOT_MINUTES / 60.0


def iter_scheduling_violations(bookings: list[Booking]) -> Iterable[tuple[str, str, tuple[int, ...]]]:
    """Yield ``(severity, code, message, booking_ids)`` for placement rules."""
    by_staff_day: dict[tuple[int, int], list[Booking]] = defaultdict(list)
    by_course_day: dict[tuple[int, int], list[Booking]] = defaultdict(list)
    from .booking_staff import timetable_staff_ids

    for b in bookings:
        for sid in timetable_staff_ids(b):
            by_staff_day[(sid, b.day)].append(b)
        if b.course_id is not None:
            by_course_day[(b.course_id, b.day)].append(b)

    for b in bookings:
        if b.day == FRIDAY and b.end_slot > FRIDAY_MAX_END_SLOT:
            from ..constants import slot_to_time

            end_t = slot_to_time(b.end_slot)
            yield (
                "hard",
                "friday_finish_after_6pm",
                f"Class finishes after 18:00 on {FRIDAY_LABEL} ({end_t.strftime('%H:%M')})",
                (b.id,),
            )
        if b.day == MONDAY and b.start_slot < MONDAY_MIN_START_SLOT:
            from ..constants import slot_to_time

            start_t = slot_to_time(b.start_slot)
            yield (
                "soft",
                "monday_start_before_930",
                f"Class starts before 09:30 on Monday ({start_t.strftime('%H:%M')})",
                (b.id,),
            )

    for (sid, day), day_bookings in by_staff_day.items():
        sessions = [(b.start_slot, b.end_slot) for b in day_bookings]
        for block in iter_continuous_6h_violation_blocks(sessions):
            staff_name = (
                day_bookings[0].staff.name if day_bookings[0].staff else f"staff #{sid}"
            )
            total_h = sum(e - s for s, e in block) * SLOT_MINUTES / 60.0
            yield (
                "hard",
                "staff_break_every_6h",
                f"{staff_name}: more than 6 hours teaching in a row on {DAYS[day]} "
                f"({total_h:g}h across {len(block)} classes without a 30-minute break)",
                tuple(b.id for b in day_bookings),
            )
            break

        ordered = sorted(day_bookings, key=lambda b: b.start_slot)
        for i in range(len(ordered) - 1):
            a, c = ordered[i], ordered[i + 1]
            gap = c.start_slot - a.end_slot
            if gap > MAX_IDLE_GAP_SLOTS:
                yield (
                    "soft",
                    "staff_idle_gap_over_2h",
                    f"{a.staff.name if a.staff else 'Lecturer'}: "
                    f"{gap * SLOT_MINUTES / 60:g}h gap between classes on {DAYS[day]}",
                    (a.id, c.id),
                )

        slots = _slots_for_bookings(day_bookings)
        if slots:
            hrs = _hours_from_slots(slots)
            if len(slots) < MIN_DAILY_TEACHING_SLOTS:
                yield (
                    "soft",
                    "staff_daily_hours_below_5",
                    f"{day_bookings[0].staff.name if day_bookings[0].staff else 'Lecturer'}: "
                    f"{hrs:g}h teaching on {DAYS[day]} (under 5h)",
                    tuple(b.id for b in day_bookings),
                )
            elif len(slots) > MAX_DAILY_TEACHING_SLOTS:
                yield (
                    "soft",
                    "staff_daily_hours_above_9",
                    f"{day_bookings[0].staff.name if day_bookings[0].staff else 'Lecturer'}: "
                    f"{hrs:g}h teaching on {DAYS[day]} (over 9h)",
                    tuple(b.id for b in day_bookings),
                )

    for (cid, day), day_bookings in by_course_day.items():
        slots = _slots_for_bookings(day_bookings)
        if slots:
            hrs = _hours_from_slots(slots)
            course_label = (
                day_bookings[0].course.code if day_bookings[0].course else f"course #{cid}"
            )
            if len(slots) < STUDENT_IDEAL_MIN_DAILY_TEACHING_SLOTS:
                yield (
                    "soft",
                    "student_daily_hours_below_5",
                    f"{course_label}: {hrs:g}h scheduled on {DAYS[day]} for students (under 5h)",
                    tuple(b.id for b in day_bookings),
                )
            elif len(slots) > STUDENT_IDEAL_MAX_DAILY_TEACHING_SLOTS:
                yield (
                    "soft",
                    "student_daily_hours_above_8",
                    f"{course_label}: {hrs:g}h scheduled on {DAYS[day]} for students (over 8h)",
                    tuple(b.id for b in day_bookings),
                )
        ordered = sorted(day_bookings, key=lambda b: b.start_slot)
        for i in range(len(ordered) - 1):
            a, c = ordered[i], ordered[i + 1]
            gap = c.start_slot - a.end_slot
            if gap > STUDENT_MAX_IDLE_GAP_SLOTS:
                course_label = a.course.code if a.course else f"course #{cid}"
                yield (
                    "soft",
                    "student_idle_gap_over_2h",
                    f"{course_label}: {gap * SLOT_MINUTES / 60:g}h gap between student "
                    f"classes on {DAYS[day]}",
                    (a.id, c.id),
                )

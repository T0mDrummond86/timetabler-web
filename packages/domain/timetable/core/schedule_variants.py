"""Group split semester-week bookings into one logical class schedule."""
from __future__ import annotations

from typing import Iterable

from .booking_sessions import (
    _compress_ranges,
    active_session_weeks,
    booking_runs_in_semester_week,
)
from .models import Booking


def _term_flags(b: Booking) -> tuple[bool, bool]:
    return bool(getattr(b, "in_term_1", 1)), bool(getattr(b, "in_term_2", 1))


def _placement_key(b: Booking) -> tuple[int, int, int, int, int]:
    t1, t2 = _term_flags(b)
    return (int(b.day), int(b.start_slot), int(b.end_slot), int(t1), int(t2))


def are_semester_week_variants(group: list[Booking]) -> bool:
    """True when rows are alternate semester-week schedules, not concurrent placements."""
    if len(group) <= 1:
        return False
    for i, a in enumerate(group):
        weeks_a = set(active_session_weeks(a))
        terms_a = _term_flags(a)
        for b in group[i + 1 :]:
            weeks_b = set(active_session_weeks(b))
            terms_b = _term_flags(b)
            if weeks_a & weeks_b:
                if _placement_key(a) != _placement_key(b):
                    return False
            elif terms_a != terms_b:
                return False
    return True


def schedule_group_key(b: Booking) -> tuple[int, int]:
    """(unit_id, session_part) — bookings sharing this are one class on a course."""
    return (int(b.unit_id or 0), int(getattr(b, "session_part", 1) or 1))


def group_schedule_bookings(bookings: Iterable[Booking]) -> dict[tuple[int, int], list[Booking]]:
    groups: dict[tuple[int, int], list[Booking]] = {}
    for b in bookings:
        groups.setdefault(schedule_group_key(b), []).append(b)
    return groups


def primary_booking(bookings: list[Booking]) -> Booking:
    """The main timetable row — most active semester weeks, then lowest id."""
    return max(bookings, key=lambda b: (len(active_session_weeks(b)), -int(b.id)))


def booking_for_semester_week(bookings: list[Booking], week: int) -> Booking | None:
    """Which booking row runs in this semester week for this class."""
    for b in bookings:
        if booking_runs_in_semester_week(b, week):
            return b
    return None


def booking_owning_week(bookings: list[Booking], week: int) -> Booking:
    """Booking to toggle when adding/removing a week in the semester grid."""
    owner = booking_for_semester_week(bookings, week)
    if owner is not None:
        return owner
    return primary_booking(bookings)


def has_schedule_variants(bookings: Iterable[Booking]) -> bool:
    return any(
        len(g) > 1 and are_semester_week_variants(g)
        for g in group_schedule_bookings(bookings).values()
    )


def variant_week_buttons(bookings: Iterable[Booking]) -> list[tuple[str, int]]:
    """(button label, preview week) for alternate schedules, sorted by week."""
    seen_week_sets: set[frozenset[int]] = set()
    out: list[tuple[str, int]] = []
    for group in group_schedule_bookings(bookings).values():
        if len(group) <= 1:
            continue
        if not are_semester_week_variants(group):
            continue
        primary = primary_booking(group)
        for b in group:
            if b.id == primary.id:
                continue
            weeks = active_session_weeks(b)
            if not weeks:
                continue
            key = frozenset(weeks)
            if key in seen_week_sets:
                continue
            seen_week_sets.add(key)
            label = f"Wk {_compress_ranges(weeks)}"
            out.append((label, weeks[0]))
    return sorted(out, key=lambda item: item[1])


def apply_schedule_display_filter(
    bookings: list[Booking],
    *,
    semester_week: int | None = None,
    standard_only: bool = False,
) -> list[Booking]:
    """One placecard per class variant group, or every concurrent placement."""
    groups = group_schedule_bookings(bookings)
    result: list[Booking] = []
    for group in groups.values():
        if len(group) == 1:
            result.append(group[0])
            continue
        if not are_semester_week_variants(group):
            result.extend(group)
            continue
        if standard_only or semester_week is None:
            result.append(primary_booking(group))
            continue
        b = booking_for_semester_week(group, semester_week)
        if b is not None:
            result.append(b)
    return result

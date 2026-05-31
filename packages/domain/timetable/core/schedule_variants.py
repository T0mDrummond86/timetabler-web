"""Group split semester-week bookings into one logical class schedule."""
from __future__ import annotations

from typing import Iterable

from .booking_sessions import (
    _compress_ranges,
    active_session_weeks,
    booking_runs_in_semester_week,
)
from .models import Booking


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
    return any(len(g) > 1 for g in group_schedule_bookings(bookings).values())


def variant_week_buttons(bookings: Iterable[Booking]) -> list[tuple[str, int]]:
    """(button label, preview week) for alternate schedules, sorted by week."""
    seen_week_sets: set[frozenset[int]] = set()
    out: list[tuple[str, int]] = []
    for group in group_schedule_bookings(bookings).values():
        if len(group) <= 1:
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
    """One placecard per class: primary schedule, or the row active in ``semester_week``."""
    groups = group_schedule_bookings(bookings)
    if standard_only or semester_week is None:
        return [primary_booking(g) for g in groups.values()]
    result: list[Booking] = []
    for group in groups.values():
        b = booking_for_semester_week(group, semester_week)
        if b is not None:
            result.append(b)
    return result

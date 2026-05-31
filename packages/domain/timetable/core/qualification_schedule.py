"""Day/night scheduling presets for qualifications."""
from __future__ import annotations

from datetime import time

from sqlalchemy.orm import Session

from ..constants import NUM_DAYS, NUM_SLOTS, slot_to_time, time_to_slot
from .models import Qualification, QualificationTimeWindow

SCHEDULE_PERIOD_DAY = "day"
SCHEDULE_PERIOD_NIGHT = "night"
SCHEDULE_PERIODS = (SCHEDULE_PERIOD_DAY, SCHEDULE_PERIOD_NIGHT)

DAY_WINDOW_START = time(8, 30)
DAY_WINDOW_END = time(19, 0)
NIGHT_WINDOW_START = time(17, 30)
NIGHT_WINDOW_END = time(21, 30)

DAY_START_SLOT = time_to_slot(DAY_WINDOW_START)
DAY_END_SLOT = time_to_slot(DAY_WINDOW_END)
NIGHT_START_SLOT = time_to_slot(NIGHT_WINDOW_START)
NIGHT_END_SLOT = time_to_slot(NIGHT_WINDOW_END)


def normalize_schedule_period(period: str | None) -> str:
    if period == SCHEDULE_PERIOD_NIGHT:
        return SCHEDULE_PERIOD_NIGHT
    return SCHEDULE_PERIOD_DAY


def window_slots_for_period(period: str | None) -> tuple[int, int]:
    if normalize_schedule_period(period) == SCHEDULE_PERIOD_NIGHT:
        return NIGHT_START_SLOT, NIGHT_END_SLOT
    return DAY_START_SLOT, DAY_END_SLOT


def qualification_windows_for_period(period: str | None) -> list[tuple[int, int, int]]:
    """``(day, start_slot, end_slot)`` for each weekday (end exclusive)."""
    start, end = window_slots_for_period(period)
    return [(day, start, end) for day in range(NUM_DAYS)]


def _interval_fits_window(
    day: int,
    start: int,
    end: int,
    windows: list[tuple[int, int, int]],
) -> bool:
    return any(wd == day and ws <= start and we >= end for (wd, ws, we) in windows)


def qual_day_start_pairs_for_duration(
    duration_slots: int,
    windows: list[tuple[int, int, int]],
) -> list[tuple[int, int]]:
    """``(day, start_slot)`` placements where the booking fits entirely inside a qual window.

    Day/night windows are invariant — scheduling rules (e.g. Friday 18:00) must not
    be intersected here; they are handled separately in the scheduling model.
    """
    if duration_slots <= 0 or not windows:
        return []
    pairs: list[tuple[int, int]] = []
    for day in range(NUM_DAYS):
        for start in range(NUM_SLOTS - duration_slots + 1):
            end = start + duration_slots
            if _interval_fits_window(day, start, end, windows):
                pairs.append((day, start))
    return pairs


def qual_day_start_pairs_for_same_day_double(
    part1_slots: int,
    gap_slots: int,
    part2_slots: int,
    windows: list[tuple[int, int, int]],
) -> list[tuple[int, int]]:
    """Valid starts for session 1 when session 2 follows on the same day after ``gap_slots``."""
    if part1_slots <= 0 or part2_slots <= 0 or not windows:
        return []
    pairs: list[tuple[int, int]] = []
    for day in range(NUM_DAYS):
        max_start = NUM_SLOTS - (part1_slots + gap_slots + part2_slots)
        for start in range(max_start + 1):
            end2 = start + part1_slots + gap_slots + part2_slots
            if _interval_fits_window(day, start, end2, windows):
                pairs.append((day, start))
    return pairs


def schedule_period_summary(period: str | None) -> str:
    p = normalize_schedule_period(period)
    if p == SCHEDULE_PERIOD_NIGHT:
        t0, t1 = NIGHT_WINDOW_START, NIGHT_WINDOW_END
        label = "Night"
    else:
        t0, t1 = DAY_WINDOW_START, DAY_WINDOW_END
        label = "Day"
    return (
        f"{label}: {t0.strftime('%H:%M')}–{t1.strftime('%H:%M')} "
        f"(Monday–Friday, all weeks)"
    )


def qual_windows_by_qualification_id(
    session: Session,
) -> dict[int, list[tuple[int, int, int]]]:
    """Derive day/night windows from each qualification's ``schedule_period`` (read-only)."""
    out: dict[int, list[tuple[int, int, int]]] = {}
    for q in session.query(Qualification).all():
        out[q.id] = qualification_windows_for_period(
            getattr(q, "schedule_period", None)
        )
    return out


def ensure_all_qualification_time_windows(session: Session) -> int:
    """Sync ``qualification_time_window`` rows from each qualification's day/night setting.

    Returns the number of qualifications whose windows were rewritten.
    """
    updated = 0
    for q in session.query(Qualification).all():
        period = normalize_schedule_period(getattr(q, "schedule_period", None))
        expected = set(qualification_windows_for_period(period))
        existing = session.query(QualificationTimeWindow).filter_by(qualification_id=q.id).all()
        actual = {(w.day, w.start_slot, w.end_slot) for w in existing}
        if actual != expected:
            replace_qualification_time_windows(session, q)
            updated += 1
    if updated:
        session.flush()
    return updated


def replace_qualification_time_windows(session: Session, qualification: Qualification) -> None:
    """Rewrite time windows from the qualification's day/night setting."""
    period = normalize_schedule_period(getattr(qualification, "schedule_period", None))
    qualification.schedule_period = period
    for w in session.query(QualificationTimeWindow).filter_by(qualification_id=qualification.id).all():
        session.delete(w)
    for day, start, end in qualification_windows_for_period(period):
        session.add(
            QualificationTimeWindow(
                qualification_id=qualification.id,
                day=day,
                start_slot=start,
                end_slot=end,
            )
        )

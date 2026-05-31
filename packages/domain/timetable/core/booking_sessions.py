"""Per-semester-week session schedule for timetable bookings.

Each booking placed in the repeating week view defaults to all applicable
semester weeks (10 for a single term, 20 for both). Users can deactivate
individual weeks in the course semester schedule view.
"""
from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy.orm import Session

from .models import Booking

SEMESTER_WEEKS = 20
TERM1_WEEKS = 10
TERM2_WEEKS = 10
TERM1_WEEK_RANGE = range(1, TERM1_WEEKS + 1)
TERM2_WEEK_RANGE = range(TERM1_WEEKS + 1, SEMESTER_WEEKS + 1)


def default_session_weeks(*, in_term_1: bool, in_term_2: bool) -> list[int]:
    """Week numbers 1–20 that apply when a booking is first placed."""
    weeks: list[int] = []
    if in_term_1:
        weeks.extend(TERM1_WEEK_RANGE)
    if in_term_2:
        weeks.extend(TERM2_WEEK_RANGE)
    return weeks


def parse_session_weeks(raw: str | None) -> list[int] | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, list):
        return None
    out: list[int] = []
    for item in data:
        try:
            w = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= w <= SEMESTER_WEEKS:
            out.append(w)
    return sorted(set(out))


def serialize_session_weeks(weeks: Iterable[int]) -> str:
    return json.dumps(sorted({int(w) for w in weeks if 1 <= int(w) <= SEMESTER_WEEKS}))


def _term_flag_enabled(value: object) -> bool:
    """Interpret unset in-memory term flags as enabled defaults."""
    if value is None:
        return True
    return bool(value)


def full_session_weeks_for_booking(booking: Booking) -> list[int]:
    """All semester weeks this booking could run in (from term flags)."""
    return default_session_weeks(
        in_term_1=_term_flag_enabled(getattr(booking, "in_term_1", 1)),
        in_term_2=_term_flag_enabled(getattr(booking, "in_term_2", 1)),
    )


def active_session_weeks(booking: Booking) -> list[int]:
    """Active week numbers; unset storage means all applicable weeks."""
    stored = parse_session_weeks(getattr(booking, "session_weeks", None))
    full = full_session_weeks_for_booking(booking)
    if stored is None:
        return list(full)
    allowed = set(full)
    return sorted(w for w in stored if w in allowed)


def active_session_weeks_in_term(booking: Booking, term: int) -> list[int]:
    """Active weeks limited to term 1 (weeks 1–10) or term 2 (11–20)."""
    if term == 1:
        span = set(TERM1_WEEK_RANGE)
    else:
        span = set(TERM2_WEEK_RANGE)
    return sorted(w for w in active_session_weeks(booking) if w in span)


def is_full_session_schedule(booking: Booking) -> bool:
    return active_session_weeks(booking) == full_session_weeks_for_booking(booking)


def session_count(booking: Booking) -> int:
    return len(active_session_weeks(booking))


def semester_weeks_denominator(booking: Booking) -> int:
    """Weeks used when averaging load across the semester (always 20)."""
    return SEMESTER_WEEKS


def session_factor(booking: Booking) -> float:
    """Fraction of the semester this booking runs (active ÷ 20)."""
    return float(session_count(booking)) / float(SEMESTER_WEEKS)


def initialize_session_weeks(booking: Booking) -> None:
    """Set default active weeks when a booking is created."""
    if parse_session_weeks(getattr(booking, "session_weeks", None)) is not None:
        return
    booking.session_weeks = serialize_session_weeks(full_session_weeks_for_booking(booking))


def set_active_session_weeks(booking: Booking, weeks: Iterable[int]) -> None:
    full = set(full_session_weeks_for_booking(booking))
    active = sorted(w for w in weeks if w in full)
    if active == sorted(full):
        booking.session_weeks = serialize_session_weeks(active)
    else:
        booking.session_weeks = serialize_session_weeks(active)


def toggle_session_week(booking: Booking, week_number: int) -> list[int]:
    """Add or remove one week; returns the new active week list."""
    full = set(full_session_weeks_for_booking(booking))
    if week_number not in full:
        return active_session_weeks(booking)
    current = set(active_session_weeks(booking))
    if week_number in current:
        current.remove(week_number)
    else:
        current.add(week_number)
    set_active_session_weeks(booking, current)
    return active_session_weeks(booking)


def booking_runs_in_semester_week(booking: Booking, week_number: int) -> bool:
    return week_number in active_session_weeks(booking)


def clone_booking_scheduling(src: Booking) -> Booking:
    """Copy scheduling fields onto a new unsaved booking row."""
    return Booking(
        week_id=src.week_id,
        course_id=src.course_id,
        unit_id=src.unit_id,
        staff_id=src.staff_id,
        sfs_co_teacher_staff_id=getattr(src, "sfs_co_teacher_staff_id", None),
        sfs_co_teacher_in_term_1=getattr(src, "sfs_co_teacher_in_term_1", 0) or 0,
        sfs_co_teacher_in_term_2=getattr(src, "sfs_co_teacher_in_term_2", 0) or 0,
        room_id=src.room_id,
        day=src.day,
        start_slot=src.start_slot,
        end_slot=src.end_slot,
        notes=src.notes,
        external_id=src.external_id,
        in_term_1=src.in_term_1,
        in_term_2=src.in_term_2,
        online_student_count=getattr(src, "online_student_count", None),
        lock_time=getattr(src, "lock_time", 0) or 0,
        lock_staff=getattr(src, "lock_staff", 0) or 0,
        session_part=getattr(src, "session_part", 1) or 1,
        session_weeks=getattr(src, "session_weeks", None),
        block_week_index=getattr(src, "block_week_index", None),
    )


def isolate_booking_for_semester_week(
    session: Session,
    booking: Booking,
    semester_week: int,
) -> Booking:
    """Ensure edits apply to a single semester week (split row when needed)."""
    weeks = active_session_weeks(booking)
    if semester_week not in weeks:
        return booking
    if len(weeks) == 1:
        return booking
    remaining = sorted(w for w in weeks if w != semester_week)
    set_active_session_weeks(booking, remaining)
    clone = clone_booking_scheduling(booking)
    set_active_session_weeks(clone, [semester_week])
    session.add(clone)
    session.flush()
    return clone


def detach_semester_week(session: Session, booking: Booking, semester_week: int) -> str:
    """Remove one semester week from a booking; delete row if it was the only week."""
    weeks = active_session_weeks(booking)
    if semester_week not in weeks:
        return "noop"
    if len(weeks) <= 1:
        session.delete(booking)
        return "deleted"
    set_active_session_weeks(booking, [w for w in weeks if w != semester_week])
    return "detached"


def _compress_ranges(weeks: list[int]) -> str:
    if not weeks:
        return ""
    parts: list[str] = []
    start = prev = weeks[0]
    for w in weeks[1:]:
        if w == prev + 1:
            prev = w
            continue
        parts.append(f"{start}" if start == prev else f"{start}–{prev}")
        start = prev = w
    parts.append(f"{start}" if start == prev else f"{start}–{prev}")
    return ", ".join(parts)


def format_session_weeks_label(
    booking: Booking,
    *,
    term: str | None = None,
) -> str | None:
    """Human label for partial schedules, e.g. ``Wks 1–8, 11–20``."""
    if is_full_session_schedule(booking):
        return None
    if term == "t1":
        active = active_session_weeks_in_term(booking, 1)
        full = [w for w in full_session_weeks_for_booking(booking) if w in TERM1_WEEK_RANGE]
        if active == full:
            return None
        if not active:
            return None
        return f"Wks {_compress_ranges(active)}"
    if term == "t2":
        active = active_session_weeks_in_term(booking, 2)
        full = [w for w in full_session_weeks_for_booking(booking) if w in TERM2_WEEK_RANGE]
        if active == full:
            return None
        if not active:
            return None
        return f"Wks {_compress_ranges(active)}"
    active = active_session_weeks(booking)
    if not active:
        return None
    return f"Wks {_compress_ranges(active)}"


def format_session_avg_line(booking: Booking, hours_per_session: float) -> str | None:
    """One line for staff tab detail: ``8 sess × 3.00h ÷ 20 wks = 1.20h/wk``."""
    n = session_count(booking)
    full_n = len(full_session_weeks_for_booking(booking))
    if n >= full_n:
        return None
    denom = semester_weeks_denominator(booking)
    avg = hours_per_session * float(n) / float(denom)
    unit = booking.unit
    label = (unit.name if unit else "").strip() or f"Booking #{booking.id}"
    return f"{label}: {n} sess × {hours_per_session:.2f}h ÷ {denom} wks = {avg:.2f}h/wk"

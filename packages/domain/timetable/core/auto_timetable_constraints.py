"""Staff-side constraints for the auto-timetabler (sourced from the Staff tab)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy.orm import Session

from ..constants import DAYS, NUM_DAYS, NUM_SLOTS, slot_to_time
from .constraint_registry import DEFAULT_RELAXATION_ORDER
from .scheduling_constraints import SchedulingConstraintSettings
from .models import Staff, StaffAvailability, StaffPreference
from .staff_hours import (
    HOURS_PER_FTE,
    VARIANCE_CATEGORY_ON_TARGET,
    VARIANCE_CATEGORY_UNKNOWN,
    classify_staff_variance,
    lecturing_hours_from_fte,
    staff_hours_snapshots_by_staff_id,
    staff_tab_total_hours,
)

# Soft objective weights when assigning a class outside a lecturer's prefs.
PREF_PENALTY_PRIORITY = {1: 0, 2: 80, 3: 160}
PREF_PENALTY_NO_MATCH = 400
# Medium: prefer not to teach on the lecturer's non-teaching day (relaxable).
PENALTY_NON_TEACHING_DAY = 100

# Total (Staff tab) must match lecturing load (FTE × 21 h) within this tolerance.
FTE_TOTAL_HOURS_TOLERANCE = 0.05

# Auto-timetabler: teaching load per term should match the FTE target as closely as
# possible; ±2 hours is the ideal band shown on the Staff tab, not a hard cutoff.
FTE_TEACHING_HOURS_TOLERANCE = 2.0


@dataclass
class AutoTimetableConstraintSettings:
    """Auto-timetabler constraint toggles (Staff tab + scheduling rules)."""

    total_hours_match_fte: bool = True
    non_teaching_day: bool = True
    blocked_times: bool = True
    first_preferences: bool = True
    second_preferences: bool = True
    third_preferences: bool = True
    scheduling: SchedulingConstraintSettings = field(
        default_factory=SchedulingConstraintSettings
    )
    # Per-constraint strength override: constraint_id → strong | medium | weak.
    constraint_strengths: dict[str, str] = field(default_factory=dict)
    # Constraints to relax in order when the solver cannot find a feasible timetable.
    relaxation_order: tuple[str, ...] = field(default_factory=lambda: DEFAULT_RELAXATION_ORDER)


# Back-compat alias used by solver parameter name.
StaffConstraintSettings = AutoTimetableConstraintSettings


@dataclass(frozen=True)
class StaffConstraintRow:
    staff_id: int
    name: str
    fte: float | None
    lecturing_hours: float | None
    total_hours: float
    hours_delta: float | None
    fte_match_status: str
    non_teaching_day: int | None
    non_teaching_day_label: str
    blocked_times_summary: str
    blocked_slot_count: int
    first_prefs: str
    second_prefs: str
    third_prefs: str


def blocked_slots_from_availability(staff: Staff, session: Session) -> set[tuple[int, int]]:
    """Blocked (day, slot) pairs from the Staff tab / import grid (StaffAvailability)."""
    windows = (
        session.query(StaffAvailability)
        .filter(StaffAvailability.staff_id == staff.id)
        .all()
    )
    if not windows:
        return set()
    available: set[tuple[int, int]] = set()
    for w in windows:
        if not (0 <= w.day < NUM_DAYS):
            continue
        for s in range(max(0, w.start_slot), min(NUM_SLOTS, w.end_slot)):
            available.add((w.day, s))
    blocked: set[tuple[int, int]] = set()
    for day in range(NUM_DAYS):
        for slot in range(NUM_SLOTS):
            if (day, slot) not in available:
                blocked.add((day, slot))
    return blocked


def non_teaching_day_slots(staff: Staff) -> set[tuple[int, int]]:
    """Slots on the lecturer's non-teaching day (moderate constraint, not stored as blocks)."""
    if staff.non_teaching_day is None or not (0 <= staff.non_teaching_day < NUM_DAYS):
        return set()
    return {(staff.non_teaching_day, slot) for slot in range(NUM_SLOTS)}


def hard_blocked_slots_for_staff(
    staff: Staff,
    session: Session,
    settings: StaffConstraintSettings,
) -> set[tuple[int, int]] | None:
    """Strong constraint: slots from the blocked-times grid only."""
    if not settings.blocked_times:
        return None
    blocked = blocked_slots_from_availability(staff, session)
    return blocked if blocked else None


def unavailable_slots_for_staff(
    staff: Staff,
    session: Session,
    settings: StaffConstraintSettings,
) -> set[tuple[int, int]] | None:
    """Union of hard-blocked and non-teaching slots (display / legacy helpers)."""
    if not settings.blocked_times and not settings.non_teaching_day:
        return None
    blocked: set[tuple[int, int]] = set()
    hard = hard_blocked_slots_for_staff(staff, session, settings)
    if hard:
        blocked |= hard
    if settings.non_teaching_day:
        blocked |= non_teaching_day_slots(staff)
    return blocked if blocked else None


def valid_day_start_pairs(
    duration_slots: int,
    unavailable: set[tuple[int, int]] | None,
) -> list[tuple[int, int]]:
    """``(day, start_slot)`` placements that do not overlap unavailable slots."""
    if duration_slots <= 0 or duration_slots > NUM_SLOTS:
        return []
    if unavailable is None:
        return [
            (d, s)
            for d in range(NUM_DAYS)
            for s in range(NUM_SLOTS - duration_slots + 1)
        ]
    pairs: list[tuple[int, int]] = []
    for day in range(NUM_DAYS):
        for start in range(NUM_SLOTS - duration_slots + 1):
            if all((day, t) not in unavailable for t in range(start, start + duration_slots)):
                pairs.append((day, start))
    return pairs


def fte_teaching_hours_tolerance_slots() -> int:
    """± tolerance in half-hour slots (from :data:`FTE_TEACHING_HOURS_TOLERANCE`)."""
    from ..constants import SLOT_MINUTES

    slots_per_hour = 60 // SLOT_MINUTES
    return int(round(FTE_TEACHING_HOURS_TOLERANCE * slots_per_hour))


def staff_target_timetable_slot_cap(staff: Staff) -> int | None:
    """Target half-hour teaching slots per term from FTE minus non-timetabled hours (Staff tab)."""
    lh = lecturing_hours_from_fte(staff.fte)
    if lh is None:
        return None
    fixed_h = sum(
        float(x or 0.0)
        for x in (
            getattr(staff, "development_project_hours", None),
            getattr(staff, "tae_hours", None),
            getattr(staff, "supervision_hours", None),
        )
    )
    target_h = lh - fixed_h
    if target_h <= 0:
        return 0
    return int(round(target_h * 2))


def fte_teaching_slot_band(staff: Staff) -> tuple[int, int, int] | None:
    """``(min_slots, target_slots, max_slots)`` per term from FTE, or ``None`` if FTE unset."""
    target = staff_target_timetable_slot_cap(staff)
    if target is None:
        return None
    tol = fte_teaching_hours_tolerance_slots()
    return (max(0, target - tol), target, target + tol)


def staff_preference_penalty(
    staff_id: int,
    unit_id: int | None,
    *,
    session: Session,
    settings: StaffConstraintSettings,
    unit_by_name: dict[str, int],
) -> int:
    """Objective penalty for assigning ``unit_id`` to ``staff_id`` (lower is better)."""
    if unit_id is None:
        return 0
    enabled_priorities = [
        p
        for p, on in (
            (1, settings.first_preferences),
            (2, settings.second_preferences),
            (3, settings.third_preferences),
        )
        if on
    ]
    if not enabled_priorities:
        return 0
    prefs = (
        session.query(StaffPreference)
        .filter(
            StaffPreference.staff_id == staff_id,
            StaffPreference.priority.in_(enabled_priorities),
        )
        .all()
    )
    if not prefs:
        return 0
    pref_unit_ids: set[int] = set()
    for p in prefs:
        if p.unit_id is not None:
            pref_unit_ids.add(p.unit_id)
        elif p.class_name:
            uid = unit_by_name.get(p.class_name.strip().lower())
            if uid is not None:
                pref_unit_ids.add(uid)
    if unit_id in pref_unit_ids:
        best = min(
            PREF_PENALTY_PRIORITY[p.priority]
            for p in prefs
            if (p.unit_id == unit_id)
            or (
                p.class_name
                and unit_by_name.get(p.class_name.strip().lower()) == unit_id
            )
        )
        return best
    return PREF_PENALTY_NO_MATCH


def effective_staff_blocked_slots(staff: Staff, session: Session) -> set[tuple[int, int]]:
    """Blocked (day, slot) pairs as shown on the Staff tab (display helper)."""
    return (
        unavailable_slots_for_staff(
            staff,
            session,
            StaffConstraintSettings(blocked_times=True, non_teaching_day=True),
        )
        or set()
    )


def format_blocked_times_summary(blocked: Iterable[tuple[int, int]]) -> str:
    """Human-readable blocked windows, e.g. ``Monday 08:00–12:00``."""
    blocked_set = set(blocked)
    if not blocked_set:
        return "—"
    parts: list[str] = []
    for day in range(5):
        slots = sorted(s for d, s in blocked_set if d == day)
        if not slots:
            continue
        ranges: list[tuple[int, int]] = []
        start = prev = slots[0]
        for s in slots[1:]:
            if s == prev + 1:
                prev = s
            else:
                ranges.append((start, prev + 1))
                start = prev = s
        ranges.append((start, prev + 1))
        for slot_start, slot_end_excl in ranges:
            t0 = slot_to_time(slot_start).strftime("%H:%M")
            t1 = slot_to_time(slot_end_excl).strftime("%H:%M")
            parts.append(f"{DAYS[day]} {t0}–{t1}")
    return "; ".join(parts) if parts else "—"


def _prefs_text(prefs: list[StaffPreference], priority: int) -> str:
    names = [
        (p.class_name or "").strip()
        for p in prefs
        if p.priority == priority and (p.class_name or "").strip()
    ]
    return ", ".join(names) if names else "—"


def staff_constraint_rows(session: Session) -> list[StaffConstraintRow]:
    """One row per lecturer with constraint data mirrored from the Staff tab."""
    staff_list = session.query(Staff).order_by(Staff.name).all()
    snaps = staff_hours_snapshots_by_staff_id(session)
    rows: list[StaffConstraintRow] = []
    for s in staff_list:
        snap = snaps[s.id]
        total = staff_tab_total_hours(s, snap)
        lh = lecturing_hours_from_fte(s.fte)
        delta = (total - lh) if lh is not None else None
        category = classify_staff_variance(
            fte=s.fte,
            lecturing_hours=lh,
            total_hours=total,
            tolerance=FTE_TOTAL_HOURS_TOLERANCE,
        )
        if category == VARIANCE_CATEGORY_ON_TARGET:
            fte_status = "OK"
        elif category == VARIANCE_CATEGORY_UNKNOWN:
            fte_status = "FTE not set"
        else:
            assert delta is not None
            sign = "+" if delta > 0 else ""
            fte_status = f"{sign}{delta:.2f} h vs target"

        prefs = (
            session.query(StaffPreference)
            .filter(StaffPreference.staff_id == s.id)
            .order_by(StaffPreference.priority, StaffPreference.slot_number)
            .all()
        )
        blocked = blocked_slots_from_availability(s, session)
        nt_day = s.non_teaching_day
        if nt_day is not None and 0 <= nt_day < len(DAYS):
            nt_label = DAYS[nt_day]
        else:
            nt_label = "—"

        rows.append(
            StaffConstraintRow(
                staff_id=s.id,
                name=s.name,
                fte=s.fte,
                lecturing_hours=lh,
                total_hours=total,
                hours_delta=delta,
                fte_match_status=fte_status,
                non_teaching_day=nt_day if nt_day is not None and 0 <= nt_day < 5 else None,
                non_teaching_day_label=nt_label,
                blocked_times_summary=format_blocked_times_summary(blocked),
                blocked_slot_count=len(blocked),
                first_prefs=_prefs_text(prefs, 1),
                second_prefs=_prefs_text(prefs, 2),
                third_prefs=_prefs_text(prefs, 3),
            )
        )
    return rows


def staff_constraint_summary(rows: list[StaffConstraintRow]) -> tuple[int, int]:
    """Return (lecturers on FTE target, total lecturers)."""
    on_target = sum(1 for r in rows if r.fte_match_status == "OK")
    return on_target, len(rows)

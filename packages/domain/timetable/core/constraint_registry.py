"""Unified auto-timetable constraint catalog (strength, enable, relaxation)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .auto_timetable_constraints import AutoTimetableConstraintSettings

# Staff-side constraint ids (stable for settings / UI).
STEP_FTE_HOURS = "fte_hours"
STEP_NON_TEACHING_DAY = "non_teaching_day"
STEP_BLOCKED_TIMES = "blocked_times"
STEP_CLASS_PREFERENCES = "class_preferences"
STEP_FIRST_PREFERENCES = "first_preferences"
STEP_SECOND_PREFERENCES = "second_preferences"
STEP_THIRD_PREFERENCES = "third_preferences"

# Legacy per-tier ids (solver flags); hidden from strength UI, merged in relaxation.
PREFERENCE_TIER_IDS: frozenset[str] = frozenset(
    {STEP_FIRST_PREFERENCES, STEP_SECOND_PREFERENCES, STEP_THIRD_PREFERENCES}
)

# Scheduling constraint ids.
STEP_BREAK_6H = "break_6h"
STEP_FRIDAY_6PM = "friday_6pm"
STEP_MONDAY_START = "monday_start_after_930"
STEP_STUDENT_DAILY_HOURS = "student_daily_hours_5_to_9"
STEP_STUDENT_BREAK_MAX = "student_break_max_2_hours"
STEP_STAFF_DAILY_HOURS = "staff_daily_hours_5_to_9"
STEP_MAX_IDLE_GAP = "max_idle_gap_2_hours"

STRENGTH_STRONG = "strong"
STRENGTH_MEDIUM = "medium"
STRENGTH_WEAK = "weak"
STRENGTHS = (STRENGTH_STRONG, STRENGTH_MEDIUM, STRENGTH_WEAK)

QUAL_WINDOWS_LABEL = "Qualification time windows"
STEP_QUAL_WINDOWS = "qual_windows"

DEFAULT_RELAXATION_ORDER: tuple[str, ...] = (
    STEP_FTE_HOURS,
    STEP_BREAK_6H,
    STEP_FRIDAY_6PM,
    STEP_BLOCKED_TIMES,
)

# Constraint id → ``SchedulingConstraintSettings`` attribute name.
SCHEDULING_SETTING_ATTRS: dict[str, str] = {
    STEP_BREAK_6H: "break_every_6_hours",
    STEP_FRIDAY_6PM: "friday_finish_by_6pm",
    STEP_MONDAY_START: "monday_start_after_930",
    STEP_STUDENT_DAILY_HOURS: "student_daily_hours_5_to_9",
    STEP_STUDENT_BREAK_MAX: "student_break_max_2_hours",
    STEP_STAFF_DAILY_HOURS: "staff_daily_hours_5_to_9",
    STEP_MAX_IDLE_GAP: "max_idle_gap_2_hours",
}


@dataclass(frozen=True)
class ConstraintDefinition:
    constraint_id: str
    label: str
    default_strength: str
    category: str  # "staff" | "scheduling"
    show_in_strength_ui: bool = True


def constraint_catalog() -> dict[str, ConstraintDefinition]:
    return {
        STEP_FTE_HOURS: ConstraintDefinition(
            STEP_FTE_HOURS,
            "Balance teaching load to FTE allocation (ideally within ±2 h per term)",
            STRENGTH_MEDIUM,
            "staff",
        ),
        STEP_NON_TEACHING_DAY: ConstraintDefinition(
            STEP_NON_TEACHING_DAY, "Non-teaching day", STRENGTH_MEDIUM, "staff"
        ),
        STEP_BLOCKED_TIMES: ConstraintDefinition(
            STEP_BLOCKED_TIMES, "Blocked times", STRENGTH_STRONG, "staff"
        ),
        STEP_CLASS_PREFERENCES: ConstraintDefinition(
            STEP_CLASS_PREFERENCES,
            "Lecturer class preferences",
            STRENGTH_WEAK,
            "staff",
            show_in_strength_ui=False,
        ),
        STEP_FIRST_PREFERENCES: ConstraintDefinition(
            STEP_FIRST_PREFERENCES,
            "1st preferences",
            STRENGTH_WEAK,
            "staff",
            show_in_strength_ui=False,
        ),
        STEP_SECOND_PREFERENCES: ConstraintDefinition(
            STEP_SECOND_PREFERENCES,
            "2nd preferences",
            STRENGTH_WEAK,
            "staff",
            show_in_strength_ui=False,
        ),
        STEP_THIRD_PREFERENCES: ConstraintDefinition(
            STEP_THIRD_PREFERENCES,
            "3rd preferences",
            STRENGTH_WEAK,
            "staff",
            show_in_strength_ui=False,
        ),
        STEP_BREAK_6H: ConstraintDefinition(
            STEP_BREAK_6H,
            "No more than 6 hours teaching in a row without a 30-minute break (per lecturer, per day)",
            STRENGTH_STRONG,
            "scheduling",
        ),
        STEP_FRIDAY_6PM: ConstraintDefinition(
            STEP_FRIDAY_6PM, "No class finishing after 18:00 on Friday",
            STRENGTH_STRONG,
            "scheduling",
        ),
        STEP_MONDAY_START: ConstraintDefinition(
            STEP_MONDAY_START, "Avoid Monday starts before 09:30",
            STRENGTH_MEDIUM,
            "scheduling",
        ),
        STEP_STUDENT_DAILY_HOURS: ConstraintDefinition(
            STEP_STUDENT_DAILY_HOURS,
            "Student cohort 5–8 hours of classes per day (ideal)",
            STRENGTH_MEDIUM,
            "scheduling",
        ),
        STEP_STUDENT_BREAK_MAX: ConstraintDefinition(
            STEP_STUDENT_BREAK_MAX,
            "Student breaks between classes ≤ 2 hours",
            STRENGTH_MEDIUM,
            "scheduling",
        ),
        STEP_STAFF_DAILY_HOURS: ConstraintDefinition(
            STEP_STAFF_DAILY_HOURS,
            "Staff daily teaching 5–9 hours (days they teach)",
            STRENGTH_WEAK,
            "scheduling",
        ),
        STEP_MAX_IDLE_GAP: ConstraintDefinition(
            STEP_MAX_IDLE_GAP,
            "Staff idle gaps ≤ 2 hours (same lecturer, same day)",
            STRENGTH_WEAK,
            "scheduling",
        ),
    }


def effective_strength(settings: AutoTimetableConstraintSettings, constraint_id: str) -> str:
    override = settings.constraint_strengths.get(constraint_id)
    if override in STRENGTHS:
        return override
    info = constraint_catalog().get(constraint_id)
    if info is None:
        return STRENGTH_MEDIUM
    return info.default_strength


def is_constraint_enabled(settings: AutoTimetableConstraintSettings, constraint_id: str) -> bool:
    if constraint_id == STEP_FTE_HOURS:
        return settings.total_hours_match_fte
    if constraint_id == STEP_NON_TEACHING_DAY:
        return settings.non_teaching_day
    if constraint_id == STEP_BLOCKED_TIMES:
        return settings.blocked_times
    if constraint_id == STEP_QUAL_WINDOWS:
        return True
    if constraint_id == STEP_CLASS_PREFERENCES:
        return (
            settings.first_preferences
            or settings.second_preferences
            or settings.third_preferences
        )
    if constraint_id == STEP_FIRST_PREFERENCES:
        return settings.first_preferences
    if constraint_id == STEP_SECOND_PREFERENCES:
        return settings.second_preferences
    if constraint_id == STEP_THIRD_PREFERENCES:
        return settings.third_preferences
    attr = SCHEDULING_SETTING_ATTRS.get(constraint_id)
    if attr is not None:
        return bool(getattr(settings.scheduling, attr, False))
    return False


def set_constraint_enabled(
    settings: AutoTimetableConstraintSettings, constraint_id: str, enabled: bool
) -> None:
    if constraint_id == STEP_FTE_HOURS:
        settings.total_hours_match_fte = enabled
    elif constraint_id == STEP_NON_TEACHING_DAY:
        settings.non_teaching_day = enabled
    elif constraint_id == STEP_BLOCKED_TIMES:
        settings.blocked_times = enabled
    elif constraint_id == STEP_CLASS_PREFERENCES:
        settings.first_preferences = enabled
        settings.second_preferences = enabled
        settings.third_preferences = enabled
    elif constraint_id == STEP_FIRST_PREFERENCES:
        settings.first_preferences = enabled
    elif constraint_id == STEP_SECOND_PREFERENCES:
        settings.second_preferences = enabled
    elif constraint_id == STEP_THIRD_PREFERENCES:
        settings.third_preferences = enabled
    else:
        attr = SCHEDULING_SETTING_ATTRS.get(constraint_id)
        if attr is not None:
            setattr(settings.scheduling, attr, enabled)


def set_constraint_strength(
    settings: AutoTimetableConstraintSettings, constraint_id: str, strength: str
) -> None:
    if strength not in STRENGTHS:
        return
    settings.constraint_strengths[constraint_id] = strength


def constraints_for_summary(settings: AutoTimetableConstraintSettings) -> list[str]:
    """Constraint ids shown in the auto-timetable summary (strength boxes only)."""
    return [
        cid
        for cid, info in constraint_catalog().items()
        if info.show_in_strength_ui
    ]


def constraints_by_strength(settings: AutoTimetableConstraintSettings) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {s: [] for s in STRENGTHS}
    for cid, info in constraint_catalog().items():
        if not info.show_in_strength_ui:
            continue
        grouped[effective_strength(settings, cid)].append(cid)
    for s in STRENGTHS:
        grouped[s].sort(key=lambda c: constraint_catalog()[c].label)
    return grouped


def lexicographic_order(
    order: list[str] | tuple[str, ...] | None,
    *,
    include_qual_windows: bool = False,
) -> tuple[str, ...]:
    """Pipeline order for lexicographic passes (top = sacrifice first).

    Day/night qualification windows are always hard constraints during auto-timetable
  and are not part of this compromise order.
    """
    steps = normalize_relaxation_order(order)
    if include_qual_windows and STEP_QUAL_WINDOWS not in steps:
        steps = steps + (STEP_QUAL_WINDOWS,)
    return steps


# Strong staff rules — must be in the lex order when enabled, or the solver treats them as hard.
_STAFF_LEX_TAIL: tuple[str, ...] = (
    STEP_BLOCKED_TIMES,
    STEP_NON_TEACHING_DAY,
)

# Medium staff rules (auto-appended after strong scheduling rules).
_MEDIUM_STAFF_LEX: tuple[str, ...] = (STEP_FTE_HOURS,)

# Strong scheduling rules (same issue if left out of the user pipeline).
_STRONG_SCHEDULING_LEX_TAIL: tuple[str, ...] = (
    STEP_BREAK_6H,
    STEP_FRIDAY_6PM,
)

# Medium / weak scheduling rules appended after user pipeline (sacrificed later = protected more).
_SCHEDULING_LEX_TAIL: tuple[str, ...] = (
    STEP_STUDENT_BREAK_MAX,
    STEP_MONDAY_START,
    STEP_STAFF_DAILY_HOURS,
    STEP_MAX_IDLE_GAP,
)

_AUTO_LEX_APPEND_ORDER: tuple[str, ...] = (
    _STAFF_LEX_TAIL
    + _STRONG_SCHEDULING_LEX_TAIL
    + (STEP_STUDENT_DAILY_HOURS,)
    + _MEDIUM_STAFF_LEX
    + _SCHEDULING_LEX_TAIL
)


def placement_lex_order(
    settings: AutoTimetableConstraintSettings,
) -> tuple[str, ...]:
    """Phase 1: time + room + cohort days (no lecturer load rules)."""
    steps: list[str] = []
    if is_constraint_enabled(settings, STEP_STUDENT_DAILY_HOURS):
        steps.append(STEP_STUDENT_DAILY_HOURS)
    return tuple(steps)


def staff_lex_order(
    settings: AutoTimetableConstraintSettings,
) -> tuple[str, ...]:
    """Phase 2: assign lecturers after placements are fixed."""
    steps: list[str] = []
    for cid in (
        STEP_MAX_IDLE_GAP,
        STEP_FTE_HOURS,
        STEP_BLOCKED_TIMES,
        STEP_NON_TEACHING_DAY,
    ):
        if is_constraint_enabled(settings, cid):
            steps.append(cid)
    return tuple(steps)


def full_lexicographic_order(
    settings: AutoTimetableConstraintSettings,
) -> tuple[str, ...]:
    """User pipeline first, then any enabled rules not yet listed (lex-soft, not hard)."""
    steps: list[str] = list(normalize_relaxation_order(settings.relaxation_order))
    seen = set(steps)
    for cid in _AUTO_LEX_APPEND_ORDER:
        if cid in seen:
            continue
        if is_constraint_enabled(settings, cid):
            steps.append(cid)
            seen.add(cid)
    if is_constraint_enabled(settings, STEP_STUDENT_DAILY_HOURS):
        steps = [STEP_STUDENT_DAILY_HOURS] + [s for s in steps if s != STEP_STUDENT_DAILY_HOURS]
    return tuple(steps)


def hard_lex_constraint_warnings(
    settings: AutoTimetableConstraintSettings,
    lex_order: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Rules that would be enforced as hard during lexicographic auto-solve (usually a mistake)."""
    order = lex_order if lex_order is not None else full_lexicographic_order(settings)
    lex_soft = set(order)
    lines: list[str] = []
    checks: tuple[tuple[str, bool, str], ...] = (
        (
            STEP_FTE_HOURS,
            settings.total_hours_match_fte,
            "FTE teaching hours within ±2 h of allocation",
        ),
        (STEP_BLOCKED_TIMES, settings.blocked_times, "Blocked times"),
        (STEP_NON_TEACHING_DAY, settings.non_teaching_day, "Non-teaching day"),
        (
            STEP_BREAK_6H,
            settings.scheduling.break_every_6_hours,
            "6 hours teaching in a row (30-minute break between classes)",
        ),
        (STEP_FRIDAY_6PM, settings.scheduling.friday_finish_by_6pm, "Friday 18:00 finish"),
    )
    for cid, enabled, label in checks:
        if not enabled:
            continue
        if effective_strength(settings, cid) == STRENGTH_STRONG and cid not in lex_soft:
            lines.append(
                f"{label} are hard constraints (not in the relaxation pipeline) — "
                "large weeks are often infeasible; add them to the pipeline or turn them off."
            )
    return tuple(lines)


def constraint_step_label(
    step_id: str, settings: AutoTimetableConstraintSettings | None = None
) -> str:
    catalog = constraint_catalog()
    if step_id == STEP_QUAL_WINDOWS:
        return QUAL_WINDOWS_LABEL
    info = catalog.get(step_id)
    if info is None:
        return step_id
    if step_id == STEP_CLASS_PREFERENCES:
        return info.label
    strength = (
        effective_strength(settings, step_id)
        if settings is not None
        else info.default_strength
    )
    return f"{info.label} ({strength})"


def normalize_relaxation_order(order: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Keep valid constraint ids in user order (pipeline is explicit, not auto-filled)."""
    catalog = constraint_catalog()
    seen: set[str] = set()
    out: list[str] = []
    for step_id in order or ():
        if step_id in PREFERENCE_TIER_IDS:
            step_id = STEP_CLASS_PREFERENCES
        if step_id in catalog and step_id not in seen:
            out.append(step_id)
            seen.add(step_id)
    return tuple(out)


def relaxation_steps_in_order(
    order: list[str] | tuple[str, ...] | None,
    settings: AutoTimetableConstraintSettings | None = None,
) -> list[tuple[str, Callable[[Any], bool], Callable[[Any], None]]]:
    """Build legacy relaxation step handlers (pipeline order, first sacrificed → last)."""
    catalog = constraint_catalog()
    steps: list[tuple[str, Callable[[Any], bool], Callable[[Any], None]]] = []
    for step_id in normalize_relaxation_order(order):
        info = catalog[step_id]
        strength = (
            effective_strength(settings, step_id)
            if settings is not None
            else info.default_strength
        )
        if step_id == STEP_CLASS_PREFERENCES:
            label = info.label
        else:
            label = f"{info.label} ({strength})"
        is_active, apply_relax = _handlers_for_step(step_id)
        steps.append((label, is_active, apply_relax))
    return steps


def effective_strength_label(constraint_id: str) -> str:
    """Display strength for a constraint (default if no override stored)."""
    info = constraint_catalog().get(constraint_id)
    return info.default_strength if info else STRENGTH_MEDIUM


def _handlers_for_step(step_id: str) -> tuple[Callable[[Any], bool], Callable[[Any], None]]:
    if step_id == STEP_FTE_HOURS:
        return (
            lambda s: s.total_hours_match_fte,
            lambda s: setattr(s, "total_hours_match_fte", False),
        )
    if step_id == STEP_NON_TEACHING_DAY:
        return (
            lambda s: s.non_teaching_day,
            lambda s: setattr(s, "non_teaching_day", False),
        )
    if step_id == STEP_BLOCKED_TIMES:
        return (
            lambda s: s.blocked_times,
            lambda s: setattr(s, "blocked_times", False),
        )
    if step_id == STEP_CLASS_PREFERENCES:
        def _relax_class_preferences(s: Any) -> None:
            s.first_preferences = False
            s.second_preferences = False
            s.third_preferences = False

        return (
            lambda s: s.first_preferences or s.second_preferences or s.third_preferences,
            _relax_class_preferences,
        )
    if step_id == STEP_FIRST_PREFERENCES:
        return (
            lambda s: s.first_preferences,
            lambda s: setattr(s, "first_preferences", False),
        )
    if step_id == STEP_SECOND_PREFERENCES:
        return (
            lambda s: s.second_preferences,
            lambda s: setattr(s, "second_preferences", False),
        )
    if step_id == STEP_THIRD_PREFERENCES:
        return (
            lambda s: s.third_preferences,
            lambda s: setattr(s, "third_preferences", False),
        )
    if step_id in SCHEDULING_SETTING_ATTRS:
        attr = SCHEDULING_SETTING_ATTRS[step_id]
        return (
            lambda s, a=attr: getattr(s.scheduling, a),
            lambda s, a=attr: setattr(s.scheduling, a, False),
        )
    raise ValueError(f"unknown constraint: {step_id}")


# --- Phased auto-solve (solver.py + auto_solve.py) — UI status hints ---

SOLVER_LEX_PHASE1_IDS: frozenset[str] = frozenset({STEP_STUDENT_DAILY_HOURS})

SOLVER_LEX_PHASE2_IDS: frozenset[str] = frozenset(
    {
        STEP_MAX_IDLE_GAP,
        STEP_FTE_HOURS,
        STEP_BLOCKED_TIMES,
        STEP_NON_TEACHING_DAY,
    }
)

SOLVER_POLISH_IDS: frozenset[str] = frozenset({STEP_CLASS_PREFERENCES}) | PREFERENCE_TIER_IDS

SOLVER_HARD_WHEN_ENABLED_IDS: frozenset[str] = frozenset({STEP_BREAK_6H})

SOLVER_STORED_ONLY_IDS: frozenset[str] = frozenset(
    {
        STEP_FRIDAY_6PM,
        STEP_MONDAY_START,
        STEP_STUDENT_BREAK_MAX,
        STEP_STAFF_DAILY_HOURS,
    }
)


def constraint_solver_status(constraint_id: str) -> str:
    """How a rule is treated by the phased auto-timetable solver."""
    if constraint_id in SOLVER_LEX_PHASE1_IDS:
        return "lex_phase1"
    if constraint_id in SOLVER_LEX_PHASE2_IDS:
        return "lex_phase2"
    if constraint_id in SOLVER_POLISH_IDS:
        return "polish"
    if constraint_id in SOLVER_HARD_WHEN_ENABLED_IDS:
        return "hard_if_enabled"
    if constraint_id in SOLVER_STORED_ONLY_IDS:
        return "stored_only"
    return "other"


# Back-compat aliases (UI previously imported from solver.engine.rules).
constraint_engine_status = constraint_solver_status
ENGINE_HARD_WHEN_ENABLED = SOLVER_HARD_WHEN_ENABLED_IDS

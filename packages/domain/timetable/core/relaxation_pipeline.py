"""Configurable constraint relaxation order for auto-timetable (re-exports registry)."""
from __future__ import annotations

from .constraint_registry import (
    DEFAULT_RELAXATION_ORDER,
    QUAL_WINDOWS_LABEL,
    STEP_BLOCKED_TIMES,
    STEP_BREAK_6H,
    STEP_CLASS_PREFERENCES,
    STEP_FTE_HOURS,
    STEP_FRIDAY_6PM,
    STEP_NON_TEACHING_DAY,
    ConstraintDefinition,
    constraint_catalog,
    normalize_relaxation_order,
    relaxation_steps_in_order,
)

# Back-compat alias.
RelaxationStepInfo = ConstraintDefinition


def relaxation_step_catalog() -> dict[str, ConstraintDefinition]:
    return constraint_catalog()


def relaxation_order_labels(order: list[str] | tuple[str, ...] | None) -> list[str]:
    catalog = constraint_catalog()
    return [catalog[sid].label for sid in normalize_relaxation_order(order)]


def strong_relaxation_order(order: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Legacy helper: pipeline ids that are strong by default catalog strength."""
    from .constraint_registry import STRENGTH_STRONG

    catalog = constraint_catalog()
    return tuple(
        sid
        for sid in normalize_relaxation_order(order)
        if catalog[sid].default_strength == STRENGTH_STRONG
    )

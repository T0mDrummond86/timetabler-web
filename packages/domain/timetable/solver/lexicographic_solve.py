"""Multi-pass lexicographic optimization for auto-timetable constraints."""
from __future__ import annotations

import os

from ortools.sat.python import cp_model

from ..core.constraint_registry import constraint_step_label


def _sum_violation_vars(
    model: cp_model.CpModel, viols: list[cp_model.IntVar], name: str
) -> cp_model.IntVar | None:
    if not viols:
        return None
    if len(viols) == 1:
        return viols[0]
    # FTE slacks are slot-hour totals (not 0/1 flags); do not cap at len(viols).
    total = model.NewIntVar(0, 10_000_000, name)
    model.Add(total == sum(viols))
    return total


def _configure_solver(solver: cp_model.CpSolver, time_limit_s: float) -> None:
    solver.parameters.max_time_in_seconds = time_limit_s
    # Single worker: parallel search can leave IntVars unset in the reported solution.
    solver.parameters.num_search_workers = 1


def _allocate_lex_time(
    time_limit_s: float,
    n_lex: int,
    *,
    n_bookings: int,
    has_polish: bool,
) -> tuple[float, float, float, float]:
    """Return (seed_seconds, per_lex_seconds, polish_seconds, lex_pool_seconds)."""
    budget = max(time_limit_s, 60.0)
    polish = min(60.0, budget * 0.08) if has_polish else 0.0
    work = budget - polish
    # Keep seed modest so lex passes (especially student daily hours) get search time.
    if n_lex <= 1:
        seed = min(work * 0.15, 25.0)
        seed = max(15.0, seed)
    else:
        seed = min(work * 0.22, 40.0 if n_bookings > 50 else 30.0)
        seed = max(20.0, seed)
    lex_pool = max(20.0, work - seed)
    per_lex = lex_pool / max(n_lex, 1)
    return seed, per_lex, polish, lex_pool


def run_lexicographic(
    model: cp_model.CpModel,
    solver: cp_model.CpSolver,
    *,
    violation_vars: dict[str, cp_model.IntVar],
    order: tuple[str, ...],
    polish_terms: list,
    time_limit_s: float,
    settings=None,
    n_bookings: int = 0,
) -> tuple[int, dict[str, int]]:
    """Minimize pipeline violations in priority order, then polish placement quality.

    Top of ``order`` is sacrificed first. ``polish_terms`` (drift, preferences) run last
    and must not drown out constraint adherence — they are optimised only after lex passes.
    """
    active_order = [sid for sid in order if sid in violation_vars]
    n_lex = len(active_order)
    seed_time, per_lex, polish_time, lex_pool = _allocate_lex_time(
        time_limit_s,
        n_lex,
        n_bookings=n_bookings,
        has_polish=bool(polish_terms),
    )
    locked: dict[str, int] = {}
    last_status = cp_model.UNKNOWN
    best_feasible = cp_model.UNKNOWN

    def _note_status(status: int) -> None:
        nonlocal last_status, best_feasible
        last_status = status
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best_feasible = status

    def _solve_seed() -> int:
        # Feasibility only — do not sum violations here or lex passes start from a
        # compromised placement (e.g. student hours never consolidate).
        model.Minimize(0)
        _configure_solver(solver, seed_time)
        status = solver.Solve(model)
        _note_status(status)
        return status

    # Phase 0: find any feasible placement before lex locking.
    _solve_seed()
    if best_feasible not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        _solve_seed()

    if best_feasible not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return last_status, locked

    # Phase 1: lexicographic — lock each rule at its best achievable level.
    remaining = lex_pool
    for index, step_id in enumerate(active_order):
        vvar = violation_vars[step_id]
        model.Minimize(vvar)
        n_left = len(active_order) - index
        if index == 0 and n_lex > 1:
            step_time = remaining * 0.5
        else:
            step_time = remaining / n_left
        step_time = max(step_time, 20.0)
        _configure_solver(solver, step_time)
        status = solver.Solve(model)
        _note_status(status)
        remaining = max(0.0, remaining - step_time)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best = int(solver.Value(vvar))
            locked[step_id] = best
            model.Add(vvar <= best)

    # Phase 2: polish drift / preferences without worsening locked violations.
    if polish_terms:
        model.Minimize(sum(polish_terms))
        _configure_solver(solver, max(polish_time, 30.0))
        status = solver.Solve(model)
        _note_status(status)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for step_id in active_order:
                locked[step_id] = int(solver.Value(violation_vars[step_id]))

    return_status = (
        last_status
        if last_status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        else best_feasible
    )
    return return_status, locked


def violation_report_lines(
    locked: dict[str, int],
    *,
    settings=None,
) -> tuple[str, ...]:
    """Human-readable lines for constraints that still have violations."""
    lines: list[str] = []
    for step_id, count in locked.items():
        if count <= 0:
            continue
        label = constraint_step_label(step_id, settings)
        unit = "violation" if count == 1 else "violations"
        lines.append(f"{label}: {count} {unit}")
    return tuple(lines)


def total_violations(locked: dict[str, int]) -> int:
    return sum(max(0, v) for v in locked.values())

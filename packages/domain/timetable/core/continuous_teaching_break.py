"""Continuous teaching / 6-hour break rule (shared validation + solver helpers)."""
from __future__ import annotations

from itertools import permutations
from typing import Iterable

from ortools.sat.python import cp_model

from ..constants import NUM_SLOTS
from .models import Booking

SIX_HOUR_SLOT_WINDOW = 12  # 6 hours of teaching
MIN_BREAK_SLOTS = 1  # 30 minutes between sessions


def staff_day_sessions(
    fixed: list[Booking],
    staff_id: int,
    day: int,
    *,
    extra_start: int | None = None,
    extra_duration: int | None = None,
) -> list[tuple[int, int]]:
    """Sorted (start_slot, end_slot) sessions for one lecturer on one day."""
    sessions: list[tuple[int, int]] = []
    for b in fixed:
        if b.staff_id == staff_id and b.day == day:
            sessions.append((b.start_slot, b.end_slot))
    if extra_start is not None and extra_duration is not None:
        sessions.append((extra_start, extra_start + extra_duration))
    sessions.sort(key=lambda x: x[0])
    return sessions


def group_sessions_into_blocks(
    sessions: list[tuple[int, int]],
) -> list[list[tuple[int, int]]]:
    """Merge consecutive sessions separated by less than a 30-minute break."""
    if not sessions:
        return []
    ordered = sorted(sessions, key=lambda x: x[0])
    blocks: list[list[tuple[int, int]]] = []
    current = [ordered[0]]
    for start, end in ordered[1:]:
        if start - current[-1][1] < MIN_BREAK_SLOTS:
            current.append((start, end))
        else:
            blocks.append(current)
            current = [(start, end)]
    blocks.append(current)
    return blocks


def continuous_6h_teaching_violated(sessions: list[tuple[int, int]]) -> bool:
    """True when 2+ sessions without a 30-minute break total more than 6 hours.

    A single session may exceed 6 hours (no break is possible mid-class).
    """
    for block in group_sessions_into_blocks(sessions):
        if len(block) < 2:
            continue
        total_slots = sum(end - start for start, end in block)
        if total_slots > SIX_HOUR_SLOT_WINDOW:
            return True
    return False


def iter_continuous_6h_violation_blocks(
    sessions: list[tuple[int, int]],
) -> Iterable[list[tuple[int, int]]]:
    """Yield each violating block of sessions."""
    for block in group_sessions_into_blocks(sessions):
        if len(block) < 2:
            continue
        total_slots = sum(end - start for start, end in block)
        if total_slots > SIX_HOUR_SLOT_WINDOW:
            yield block


def add_continuous_6h_soft_violations(
    model: cp_model.CpModel,
    class_on_day: list[tuple[cp_model.IntVar, int, cp_model.IntVar]],
    *,
    max_chain_length: int = 5,
) -> list[cp_model.IntVar]:
    """Soft violations for one lecturer on one day.

    ``class_on_day`` entries are ``(active, duration_slots, start_slot_in_day)``.
  A violation is a chain of 2+ sessions in time order with < 30 minutes between
    consecutive sessions and more than 6 hours of teaching in total.
    """
    viols: list[cp_model.IntVar] = []
    n = len(class_on_day)
    if n < 2:
        return viols

    for chain_len in range(2, min(n, max_chain_length) + 1):
        for order in permutations(range(n), chain_len):
            acts = [class_on_day[i][0] for i in order]
            durs = [class_on_day[i][1] for i in order]
            starts = [class_on_day[i][2] for i in order]
            total = sum(durs)
            if total <= SIX_HOUR_SLOT_WINDOW:
                continue

            # This permutation matches the timetable only if each session follows the previous in time.
            ordered: list[cp_model.IntVar] = []
            for j in range(chain_len - 1):
                step = model.NewBoolVar(f"c6ord_{order}_{j}")
                model.Add(starts[j + 1] >= starts[j] + durs[j]).OnlyEnforceIf(step)
                model.Add(starts[j] >= starts[j + 1] + durs[j + 1]).OnlyEnforceIf(step.Not())
                ordered.append(step)

            perm_ok = model.NewBoolVar(f"c6perm_{order}")
            for step in ordered:
                model.Add(perm_ok <= step)
            model.Add(perm_ok >= sum(ordered) - (chain_len - 2))

            tight_steps: list[cp_model.IntVar] = []
            for j in range(chain_len - 1):
                gap = model.NewIntVar(-NUM_SLOTS, NUM_SLOTS, f"c6gap_{order}_{j}")
                model.Add(gap == starts[j + 1] - (starts[j] + durs[j]))
                tight = model.NewBoolVar(f"c6tight_{order}_{j}")
                model.Add(gap < MIN_BREAK_SLOTS).OnlyEnforceIf(tight)
                model.Add(gap >= MIN_BREAK_SLOTS).OnlyEnforceIf(tight.Not())
                tight_steps.append(tight)

            chain_tight = model.NewBoolVar(f"c6ctight_{order}")
            for tight in tight_steps:
                model.Add(chain_tight <= tight)
            model.Add(chain_tight >= sum(tight_steps) - (chain_len - 2))

            all_active = model.NewBoolVar(f"c6all_{order}")
            for act in acts:
                model.Add(all_active <= act)
            model.Add(all_active >= sum(acts) - (chain_len - 1))

            viol = model.NewBoolVar(f"c6viol_{order}")
            model.Add(viol <= perm_ok)
            model.Add(viol <= chain_tight)
            model.Add(viol <= all_active)
            model.Add(viol >= perm_ok + chain_tight + all_active - 2)
            viols.append(viol)

    return viols

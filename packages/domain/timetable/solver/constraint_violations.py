"""Lexicographic violation counters for auto-timetable (soften hard rules)."""
from __future__ import annotations

from ortools.sat.python import cp_model

from ..constants import NUM_DAYS, NUM_SLOTS
from ..core.auto_timetable_constraints import (
    StaffConstraintSettings,
    fte_teaching_slot_band,
    hard_blocked_slots_for_staff,
    non_teaching_day_slots,
    valid_day_start_pairs,
)
from ..core.constraint_registry import (
    STEP_BLOCKED_TIMES,
    STEP_BREAK_6H,
    STEP_CLASS_PREFERENCES,
    STEP_FTE_HOURS,
    STEP_FRIDAY_6PM,
    STEP_NON_TEACHING_DAY,
    STEP_QUAL_WINDOWS,
    is_constraint_enabled,
)
from ..core.scheduling_constraints import (
    FRIDAY,
    FRIDAY_MAX_END_SLOT,
    MIN_BREAK_SLOTS,
    SIX_HOUR_SLOT_WINDOW,
)


def _sum_vars(model: cp_model.CpModel, terms: list, name: str) -> cp_model.IntVar:
    if not terms:
        z = model.NewIntVar(0, 0, name)
        model.Add(z == 0)
        return z
    if len(terms) == 1:
        return terms[0]
    total = model.NewIntVar(0, 10_000_000, name)
    model.Add(total == sum(terms))
    return total


def build_fte_violation(
    model: cp_model.CpModel,
    *,
    movable: list,
    fixed: list,
    staff_all: dict[int, object],
    staff_presence: dict[int, dict[int | None, cp_model.IntVar]],
    durations: dict[int, int],
    terms_fn,
) -> cp_model.IntVar | None:
    """Minimize per-term teaching load gap from the FTE target (±2 h is the ideal band)."""
    slacks: list[cp_model.IntVar] = []
    for sid, s in staff_all.items():
        band = fte_teaching_slot_band(s)
        if band is None:
            continue
        _min_slots, target_slots, _max_slots = band
        for term in ("t1", "t2"):
            fixed_load = sum(
                (fb.end_slot - fb.start_slot)
                for fb in fixed
                if fb.staff_id == sid
                and (
                    (term == "t1" and bool(getattr(fb, "in_term_1", 1)))
                    or (term == "t2" and bool(getattr(fb, "in_term_2", 1)))
                )
            )
            terms_terms = []
            for b in movable:
                t1, t2 = terms_fn(b)
                if (term == "t1" and not t1) or (term == "t2" and not t2):
                    continue
                if sid in staff_presence.get(b.id, {}):
                    pres = staff_presence[b.id][sid]
                    dur = durations[b.id]
                    contrib = model.NewIntVar(0, dur, f"fte_contrib_{sid}_{b.id}_{term}")
                    model.Add(contrib == dur).OnlyEnforceIf(pres)
                    model.Add(contrib == 0).OnlyEnforceIf(pres.Not())
                    terms_terms.append(contrib)
            if not terms_terms and fixed_load == target_slots:
                continue
            load = model.NewIntVar(0, 10_000, f"fte_load_{sid}_{term}")
            if terms_terms:
                model.Add(load == sum(terms_terms) + fixed_load)
            else:
                model.Add(load == fixed_load)
            over = model.NewIntVar(0, 10_000, f"fte_over_{sid}_{term}")
            model.Add(over >= load - target_slots)
            model.Add(over >= 0)
            slacks.append(over)
            under = model.NewIntVar(0, 10_000, f"fte_under_{sid}_{term}")
            model.Add(under >= target_slots - load)
            model.Add(under >= 0)
            slacks.append(under)
    if not slacks:
        return None
    return _sum_vars(model, slacks, "viol_fte")


def build_blocked_violations(
    model: cp_model.CpModel,
    *,
    movable: list,
    staff_presence: dict[int, dict[int | None, cp_model.IntVar]],
    day_var: dict[int, cp_model.IntVar],
    start_var: dict[int, cp_model.IntVar],
    durations: dict[int, int],
    blocked_by_staff: dict[int, set[tuple[int, int]] | None],
) -> cp_model.IntVar | None:
    """One violation per (booking, lecturer) if assigned into any blocked slot."""
    viols: list[cp_model.IntVar] = []
    for b in movable:
        dur = durations[b.id]
        day = day_var[b.id]
        sd = start_var[b.id]
        for sid, pres in staff_presence[b.id].items():
            if sid is None:
                continue
            blocked = blocked_by_staff.get(sid) or set()
            if not blocked:
                continue
            valid_pairs = valid_day_start_pairs(dur, blocked)
            if not valid_pairs:
                viol = model.NewBoolVar(f"blkviol_{b.id}_{sid}")
                model.Add(viol == pres)
                viols.append(viol)
                continue
            in_valid = model.NewBoolVar(f"blkvalid_{b.id}_{sid}")
            model.AddAllowedAssignments([day, sd], valid_pairs).OnlyEnforceIf(in_valid)
            viol = model.NewBoolVar(f"blkviol_{b.id}_{sid}")
            model.Add(viol <= pres)
            model.Add(viol + in_valid >= pres)
            model.Add(viol <= 1 - in_valid)
            viols.append(viol)
    if not viols:
        return None
    return _sum_vars(model, viols, "viol_blocked")


def build_non_teaching_violation(
    model: cp_model.CpModel,
    *,
    movable: list,
    staff_all: dict[int, object],
    staff_presence: dict[int, dict[int | None, cp_model.IntVar]],
    day_var: dict[int, cp_model.IntVar],
) -> cp_model.IntVar | None:
    viols: list[cp_model.IntVar] = []
    for b in movable:
        for sid, pres in staff_presence[b.id].items():
            if sid is None:
                continue
            staff = staff_all.get(sid)
            if staff is None:
                continue
            nt = getattr(staff, "non_teaching_day", None)
            if nt is None or not (0 <= nt < NUM_DAYS):
                continue
            on_nt = model.NewBoolVar(f"ntlex_{b.id}_{sid}")
            model.Add(day_var[b.id] == nt).OnlyEnforceIf(on_nt)
            model.Add(day_var[b.id] != nt).OnlyEnforceIf(on_nt.Not())
            viol = model.NewBoolVar(f"ntlexv_{b.id}_{sid}")
            model.Add(viol <= pres)
            model.Add(viol <= on_nt)
            model.Add(viol >= pres + on_nt - 1)
            viols.append(viol)
    if not viols:
        return None
    return _sum_vars(model, viols, "viol_non_teaching")


def build_qual_window_violations(
    model: cp_model.CpModel,
    *,
    movable: list,
    day_var: dict[int, cp_model.IntVar],
    start_var: dict[int, cp_model.IntVar],
    durations: dict[int, int],
    course_qualification: dict[int, int],
    qual_windows: dict[int, list[tuple[int, int, int]]],
) -> cp_model.IntVar | None:
    viols: list[cp_model.IntVar] = []
    for b in movable:
        qid = course_qualification.get(b.course_id)
        if qid is None:
            continue
        windows = qual_windows.get(qid)
        if not windows:
            continue
        dur = durations[b.id]
        day = day_var[b.id]
        sd = start_var[b.id]
        fits = model.NewBoolVar(f"qfit_{b.id}")
        fit_terms: list[cp_model.IntVar] = []
        for wd, ws, we in windows:
            in_w = model.NewBoolVar(f"qinw_{b.id}_{wd}_{ws}")
            on_day = model.NewBoolVar(f"qday_{b.id}_{wd}")
            model.Add(day == wd).OnlyEnforceIf(on_day)
            model.Add(day != wd).OnlyEnforceIf(on_day.Not())
            start_ok = model.NewBoolVar(f"qso_{b.id}_{ws}")
            model.Add(sd >= ws).OnlyEnforceIf(start_ok)
            model.Add(sd < ws).OnlyEnforceIf(start_ok.Not())
            end_ok = model.NewBoolVar(f"qeo_{b.id}_{we}")
            model.Add(sd + dur <= we).OnlyEnforceIf(end_ok)
            model.Add(sd + dur > we).OnlyEnforceIf(end_ok.Not())
            model.Add(in_w <= on_day)
            model.Add(in_w <= start_ok)
            model.Add(in_w <= end_ok)
            model.Add(in_w >= on_day + start_ok + end_ok - 2)
            fit_terms.append(in_w)
        if fit_terms:
            model.Add(sum(fit_terms) >= 1).OnlyEnforceIf(fits)
            model.Add(sum(fit_terms) == 0).OnlyEnforceIf(fits.Not())
        else:
            model.Add(fits == 0)
        viol = model.NewBoolVar(f"qviol_{b.id}")
        model.Add(viol + fits == 1)
        viols.append(viol)
    if not viols:
        return None
    return _sum_vars(model, viols, "viol_qual")


def build_pipeline_violations(
    model: cp_model.CpModel,
    *,
    order: tuple[str, ...],
    sc: StaffConstraintSettings,
    movable: list,
    fixed: list,
    staff_all: dict[int, object],
    staff_presence: dict[int, dict[int | None, cp_model.IntVar]],
    day_var: dict[int, cp_model.IntVar],
    start_var: dict[int, cp_model.IntVar],
    durations: dict[int, int],
    blocked_by_staff: dict[int, set[tuple[int, int]] | None],
    course_qualification: dict[int, int],
    qual_windows: dict[int, list[tuple[int, int, int]]],
    terms_fn,
    scheduling_violations: dict[str, cp_model.IntVar],
) -> dict[str, cp_model.IntVar]:
    """Build total violation IntVar per pipeline step (enabled steps only)."""
    out: dict[str, cp_model.IntVar] = {}
    for step_id in order:
        if not is_constraint_enabled(sc, step_id) and step_id != STEP_QUAL_WINDOWS:
            continue
        if step_id == STEP_FTE_HOURS:
            v = build_fte_violation(
                model,
                movable=movable,
                fixed=fixed,
                staff_all=staff_all,
                staff_presence=staff_presence,
                durations=durations,
                terms_fn=terms_fn,
            )
        elif step_id == STEP_BLOCKED_TIMES:
            v = build_blocked_violations(
                model,
                movable=movable,
                staff_presence=staff_presence,
                day_var=day_var,
                start_var=start_var,
                durations=durations,
                blocked_by_staff=blocked_by_staff,
            )
        elif step_id == STEP_NON_TEACHING_DAY:
            v = build_non_teaching_violation(
                model,
                movable=movable,
                staff_all=staff_all,
                staff_presence=staff_presence,
                day_var=day_var,
            )
        elif step_id == STEP_QUAL_WINDOWS:
            v = build_qual_window_violations(
                model,
                movable=movable,
                day_var=day_var,
                start_var=start_var,
                durations=durations,
                course_qualification=course_qualification,
                qual_windows=qual_windows,
            )
        elif step_id in scheduling_violations:
            v = scheduling_violations[step_id]
        else:
            v = None
        if v is not None:
            out[step_id] = v
    return out


def prepare_blocked_by_staff(
    staff_all: dict[int, object],
    session,
    sc: StaffConstraintSettings,
    *,
    lexicographic_soft: frozenset[str],
) -> dict[int, set[tuple[int, int]] | None]:
    """Blocked slot sets for soft penalties (includes non-teaching when strong+soft)."""
    blocked: dict[int, set[tuple[int, int]] | None] = {}
    if not sc.blocked_times and not sc.non_teaching_day:
        return blocked
    for sid, s in staff_all.items():
        slots: set[tuple[int, int]] = set()
        if sc.blocked_times:
            slots |= hard_blocked_slots_for_staff(s, session, sc) or set()
        if (
            sc.non_teaching_day
            and STEP_NON_TEACHING_DAY in lexicographic_soft
        ):
            slots |= non_teaching_day_slots(s)
        blocked[sid] = slots if slots else None
    return blocked

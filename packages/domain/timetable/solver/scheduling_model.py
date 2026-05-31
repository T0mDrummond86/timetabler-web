"""CP-SAT scheduling constraints (breaks, Friday finish, Monday start, idle gaps)."""
from __future__ import annotations

from collections import defaultdict

from ortools.sat.python import cp_model

from ..constants import NUM_DAYS, NUM_SLOTS
from ..core.scheduling_constraints import (
    FRIDAY,
    FRIDAY_MAX_END_SLOT,
    MAX_DAILY_TEACHING_SLOTS,
    MAX_IDLE_GAP_SLOTS,
    MIN_BREAK_SLOTS,
    MIN_DAILY_TEACHING_SLOTS,
    MONDAY,
    MONDAY_MIN_START_SLOT,
    PENALTY_LONG_IDLE_GAP,
    PENALTY_MONDAY_EARLY_START,
    PENALTY_STAFF_DAILY_HOURS,
    PENALTY_STUDENT_DAILY_HOURS,
    PENALTY_STUDENT_LONG_IDLE,
    SIX_HOUR_SLOT_WINDOW,
    STUDENT_IDEAL_MAX_DAILY_TEACHING_SLOTS,
    STUDENT_IDEAL_MIN_DAILY_TEACHING_SLOTS,
    STUDENT_MAX_IDLE_GAP_SLOTS,
    SchedulingConstraintSettings,
    filter_day_start_pairs,
    fixed_occupied_slots_by_staff_day,
    placement_violates_6h_break,
)
from ..core.continuous_teaching_break import add_continuous_6h_soft_violations


def _sum_violation_vars(
    model: cp_model.CpModel, viols: list[cp_model.IntVar], name: str
) -> cp_model.IntVar | None:
    if not viols:
        return None
    if len(viols) == 1:
        return viols[0]
    total = model.NewIntVar(0, 10_000_000, name)
    model.Add(total == sum(viols))
    return total


def add_scheduling_constraints(
    model: cp_model.CpModel,
    *,
    movable: list,
    fixed: list,
    staff_all: dict[int, object],
    staff_presence: dict[int, dict[int | None, cp_model.IntVar]],
    day_var: dict[int, cp_model.IntVar],
    start_var: dict[int, cp_model.IntVar],
    durations: dict[int, int],
    settings: SchedulingConstraintSettings,
    auto_settings: object | None = None,
    lexicographic_soft: frozenset[str] | None = None,
    lexicographic_mode: bool = False,
) -> tuple[list, dict[str, cp_model.IntVar]]:
    """Add hard/soft scheduling rules; return (objective terms, lexicographic violation totals)."""
    from ..core.constraint_registry import (
        STEP_BREAK_6H,
        STEP_FRIDAY_6PM,
        STEP_MAX_IDLE_GAP,
        STEP_MONDAY_START,
        STEP_STAFF_DAILY_HOURS,
        STEP_STUDENT_BREAK_MAX,
        STEP_STUDENT_DAILY_HOURS,
        STRENGTH_STRONG,
        effective_strength,
    )

    sched = settings
    lex_soft = lexicographic_soft or frozenset()
    lex_violations: dict[str, cp_model.IntVar] = {}

    def _hard_scheduling(constraint_id: str, attr: str) -> bool:
        if not getattr(sched, attr, False):
            return False
        if constraint_id in lex_soft:
            return False
        if auto_settings is None:
            return True
        return effective_strength(auto_settings, constraint_id) == STRENGTH_STRONG

    if not (
        sched.break_every_6_hours
        or sched.friday_finish_by_6pm
        or sched.monday_start_after_930
        or sched.max_idle_gap_2_hours
        or sched.staff_daily_hours_5_to_9
        or sched.student_daily_hours_5_to_9
        or sched.student_break_max_2_hours
    ):
        return [], {}

    obj_terms: list = []
    fixed_occ = fixed_occupied_slots_by_staff_day(fixed)

    # Strong: nothing on Friday may end after 18:00 (or lexicographic violation).
    friday_viols: list[cp_model.IntVar] = []
    if sched.friday_finish_by_6pm:
        for b in movable:
            day = day_var[b.id]
            sd = start_var[b.id]
            dur = durations[b.id]
            is_friday = model.NewBoolVar(f"fri_{b.id}")
            model.Add(day == FRIDAY).OnlyEnforceIf(is_friday)
            model.Add(day != FRIDAY).OnlyEnforceIf(is_friday.Not())
            if _hard_scheduling(STEP_FRIDAY_6PM, "friday_finish_by_6pm"):
                model.Add(sd + dur <= FRIDAY_MAX_END_SLOT).OnlyEnforceIf(is_friday)
            elif STEP_FRIDAY_6PM in lex_soft:
                late = model.NewBoolVar(f"fri_late_{b.id}")
                model.Add(sd + dur > FRIDAY_MAX_END_SLOT).OnlyEnforceIf(late)
                model.Add(sd + dur <= FRIDAY_MAX_END_SLOT).OnlyEnforceIf(late.Not())
                viol = model.NewBoolVar(f"fri_viol_{b.id}")
                model.Add(viol <= is_friday)
                model.Add(viol <= late)
                model.Add(viol >= is_friday + late - 1)
                friday_viols.append(viol)
    if friday_viols:
        total = model.NewIntVar(0, len(friday_viols), "viol_friday")
        model.Add(total == sum(friday_viols))
        lex_violations[STEP_FRIDAY_6PM] = total

    # Medium: discourage Monday starts before 09:30.
    if sched.monday_start_after_930:
        mon_viols: list[cp_model.IntVar] = []
        for b in movable:
            day = day_var[b.id]
            sd = start_var[b.id]
            is_monday = model.NewBoolVar(f"mon_{b.id}")
            model.Add(day == MONDAY).OnlyEnforceIf(is_monday)
            model.Add(day != MONDAY).OnlyEnforceIf(is_monday.Not())
            early = model.NewBoolVar(f"mon_early_{b.id}")
            model.Add(sd < MONDAY_MIN_START_SLOT).OnlyEnforceIf(early)
            model.Add(sd >= MONDAY_MIN_START_SLOT).OnlyEnforceIf(early.Not())
            violation = model.NewBoolVar(f"mon_viol_{b.id}")
            model.Add(violation <= is_monday)
            model.Add(violation <= early)
            model.Add(violation >= is_monday + early - 1)
            if lexicographic_mode:
                mon_viols.append(violation)
            else:
                obj_terms.append(PENALTY_MONDAY_EARLY_START * violation)
        if lexicographic_mode:
            total = _sum_violation_vars(model, mon_viols, "viol_monday")
            if total is not None:
                lex_violations[STEP_MONDAY_START] = total

    teach: dict[tuple[int, int, int], cp_model.IntVar] = {}
    course_teach: dict[tuple[int, int, int], cp_model.IntVar] = {}
    need_staff_teach = (
        sched.break_every_6_hours
        or sched.max_idle_gap_2_hours
        or sched.staff_daily_hours_5_to_9
    )
    need_course_teach = sched.student_daily_hours_5_to_9 or sched.student_break_max_2_hours
    course_ids = sorted(
        {b.course_id for b in movable + fixed if b.course_id is not None}
    )

    if need_course_teach:
        course_cover: dict[tuple[int, int, int], list[cp_model.IntVar]] = defaultdict(list)
        for cid in course_ids:
            for d in range(NUM_DAYS):
                for t in range(NUM_SLOTS):
                    course_teach[(cid, d, t)] = model.NewBoolVar(f"cteach_{cid}_{d}_{t}")
        course_fixed_slots: set[tuple[int, int, int]] = set()
        for fb in fixed:
            if fb.course_id is None:
                continue
            for t in range(fb.start_slot, fb.end_slot):
                if 0 <= fb.day < NUM_DAYS and 0 <= t < NUM_SLOTS:
                    key = (fb.course_id, fb.day, t)
                    course_fixed_slots.add(key)
                    model.Add(course_teach[key] == 1)
        for b in movable:
            if b.course_id is None:
                continue
            _accumulate_booking_slot_coverage(
                model,
                b,
                day_var[b.id],
                start_var[b.id],
                durations[b.id],
                course_cover,
                b.course_id,
            )
        _finalize_teach_grid(model, course_teach, course_cover, course_fixed_slots)

    if need_staff_teach:
        staff_cover: dict[tuple[int, int, int], list[cp_model.IntVar]] = defaultdict(list)
        for sid in staff_all:
            for d in range(NUM_DAYS):
                for t in range(NUM_SLOTS):
                    teach[(sid, d, t)] = model.NewBoolVar(f"teach_{sid}_{d}_{t}")

        staff_fixed_slots: set[tuple[int, int, int]] = set()
        for fb in fixed:
            if fb.staff_id is None:
                continue
            for t in range(fb.start_slot, fb.end_slot):
                if 0 <= fb.day < NUM_DAYS and 0 <= t < NUM_SLOTS:
                    key = (fb.staff_id, fb.day, t)
                    staff_fixed_slots.add(key)
                    model.Add(teach[key] == 1)

        for b in movable:
            dur = durations[b.id]
            day = day_var[b.id]
            sd = start_var[b.id]
            for sid, pres in staff_presence[b.id].items():
                if sid is None:
                    continue
                for d in range(NUM_DAYS):
                    on_day = model.NewBoolVar(f"bd_{b.id}_{sid}_{d}")
                    model.Add(day == d).OnlyEnforceIf(on_day)
                    model.Add(day != d).OnlyEnforceIf(on_day.Not())
                    for t in range(NUM_SLOTS):
                        in_block = model.NewBoolVar(f"blk_{b.id}_{sid}_{d}_{t}")
                        ge = model.NewBoolVar(f"ge_{b.id}_{sid}_{d}_{t}")
                        lt = model.NewBoolVar(f"lt_{b.id}_{sid}_{d}_{t}")
                        model.Add(sd <= t).OnlyEnforceIf(ge)
                        model.Add(sd > t).OnlyEnforceIf(ge.Not())
                        model.Add(t < sd + dur).OnlyEnforceIf(lt)
                        model.Add(t >= sd + dur).OnlyEnforceIf(lt.Not())
                        active = model.NewBoolVar(f"bka_{b.id}_{sid}_{d}_{t}")
                        model.AddBoolAnd([pres, on_day, ge, lt]).OnlyEnforceIf(active)
                        model.AddBoolOr(
                            [pres.Not(), on_day.Not(), ge.Not(), lt.Not()]
                        ).OnlyEnforceIf(active.Not())
                        staff_cover[(sid, d, t)].append(active)
        _finalize_teach_grid(model, teach, staff_cover, staff_fixed_slots)

        break_viols: list[cp_model.IntVar] = []
        if sched.break_every_6_hours:
            for sid in staff_all:
                for d in range(NUM_DAYS):
                    class_on_day: list[tuple[cp_model.IntVar, int, cp_model.IntVar]] = []
                    for b in movable:
                        pres_map = staff_presence.get(b.id, {})
                        if sid not in pres_map:
                            continue
                        pres = pres_map[sid]
                        dur = durations[b.id]
                        day = day_var[b.id]
                        sd = start_var[b.id]
                        on_day = model.NewBoolVar(f"b6d_{b.id}_{sid}_{d}")
                        model.Add(day == d).OnlyEnforceIf(on_day)
                        model.Add(day != d).OnlyEnforceIf(on_day.Not())
                        active = model.NewBoolVar(f"b6a_{b.id}_{sid}_{d}")
                        model.Add(active <= pres)
                        model.Add(active <= on_day)
                        model.Add(active >= pres + on_day - 1)
                        class_on_day.append((active, dur, sd))
                    chain_viols = add_continuous_6h_soft_violations(model, class_on_day)
                    if _hard_scheduling(STEP_BREAK_6H, "break_every_6_hours"):
                        for viol in chain_viols:
                            model.Add(viol == 0)
                    elif STEP_BREAK_6H in lex_soft:
                        break_viols.extend(chain_viols)
        if break_viols:
            total = model.NewIntVar(0, len(break_viols), "viol_break")
            model.Add(total == sum(break_viols))
            lex_violations[STEP_BREAK_6H] = total

        if sched.max_idle_gap_2_hours:
            gap_slots = MAX_IDLE_GAP_SLOTS + 1  # 5 slots = 2.5 h idle (over 2 h limit)
            staff_idle_viols: list[cp_model.IntVar] = []
            for sid in staff_all:
                for d in range(NUM_DAYS):
                    for t0 in range(1, NUM_SLOTS - gap_slots):
                        long_idle = model.NewBoolVar(f"longidle_{sid}_{d}_{t0}")
                        before = teach[(sid, d, t0 - 1)]
                        after = teach[(sid, d, t0 + gap_slots)]
                        mids = [teach[(sid, d, t0 + k)] for k in range(gap_slots)]
                        model.Add(long_idle <= before)
                        model.Add(long_idle <= after)
                        for m in mids:
                            model.Add(long_idle <= 1 - m)
                        model.Add(
                            long_idle
                            >= before + after + sum(1 - m for m in mids) - gap_slots - 1
                        )
                        if lexicographic_mode:
                            staff_idle_viols.append(long_idle)
                        else:
                            obj_terms.append(PENALTY_LONG_IDLE_GAP * long_idle)
            if lexicographic_mode:
                total = _sum_violation_vars(model, staff_idle_viols, "viol_staff_idle")
                if total is not None:
                    lex_violations[STEP_MAX_IDLE_GAP] = total

        if sched.staff_daily_hours_5_to_9:
            if lexicographic_mode:
                staff_daily_viols = _daily_hours_band_violations(
                    model, teach, list(staff_all.keys()), "staff"
                )
                total = _sum_violation_vars(model, staff_daily_viols, "viol_staff_daily")
                if total is not None:
                    lex_violations[STEP_STAFF_DAILY_HOURS] = total
            else:
                obj_terms.extend(
                    _daily_hours_band_penalties(
                        model, teach, list(staff_all.keys()), PENALTY_STAFF_DAILY_HOURS, "staff"
                    )
                )

    if need_course_teach:
        if sched.student_daily_hours_5_to_9:
            if lexicographic_mode:
                student_daily = _student_daily_hours_slack_violation(
                    model, course_teach, course_ids
                )
                if student_daily is not None:
                    lex_violations[STEP_STUDENT_DAILY_HOURS] = student_daily
            else:
                obj_terms.extend(
                    _student_daily_hours_slack_penalties(
                        model, course_teach, course_ids, PENALTY_STUDENT_DAILY_HOURS
                    )
                )
        if sched.student_break_max_2_hours:
            gap_slots = STUDENT_MAX_IDLE_GAP_SLOTS + 1
            student_idle_viols: list[cp_model.IntVar] = []
            for cid in course_ids:
                for d in range(NUM_DAYS):
                    for t0 in range(1, NUM_SLOTS - gap_slots):
                        long_idle = model.NewBoolVar(f"stuidle_{cid}_{d}_{t0}")
                        before = course_teach[(cid, d, t0 - 1)]
                        after = course_teach[(cid, d, t0 + gap_slots)]
                        mids = [course_teach[(cid, d, t0 + k)] for k in range(gap_slots)]
                        model.Add(long_idle <= before)
                        model.Add(long_idle <= after)
                        for m in mids:
                            model.Add(long_idle <= 1 - m)
                        model.Add(
                            long_idle
                            >= before + after + sum(1 - m for m in mids) - gap_slots - 1
                        )
                        if lexicographic_mode:
                            student_idle_viols.append(long_idle)
                        else:
                            obj_terms.append(PENALTY_STUDENT_LONG_IDLE * long_idle)
            if lexicographic_mode:
                total = _sum_violation_vars(model, student_idle_viols, "viol_student_idle")
                if total is not None:
                    lex_violations[STEP_STUDENT_BREAK_MAX] = total

    return obj_terms, lex_violations


def filter_staff_day_start_pairs(
    pairs: list[tuple[int, int]],
    duration_slots: int,
    staff_id: int,
    fixed: list,
    settings: SchedulingConstraintSettings,
    auto_settings: object | None = None,
    lexicographic_soft: frozenset[str] | None = None,
) -> list[tuple[int, int]]:
    """Narrow placements for one lecturer using fixed bookings + strong rules."""
    from dataclasses import replace

    from ..core.constraint_registry import STEP_BREAK_6H, STEP_FRIDAY_6PM, STRENGTH_STRONG, effective_strength

    sched_for_filter = settings
    lex_soft = lexicographic_soft or frozenset()
    if auto_settings is not None:
        if (
            effective_strength(auto_settings, STEP_FRIDAY_6PM) != STRENGTH_STRONG
            or STEP_FRIDAY_6PM in lex_soft
        ):
            sched_for_filter = replace(settings, friday_finish_by_6pm=False)
    pairs = filter_day_start_pairs(pairs, duration_slots, sched_for_filter)
    if not settings.break_every_6_hours:
        return pairs
    if auto_settings is not None and (
        effective_strength(auto_settings, STEP_BREAK_6H) != STRENGTH_STRONG
        or STEP_BREAK_6H in lex_soft
    ):
        return pairs
    out: list[tuple[int, int]] = []
    for day, start in pairs:
        if placement_violates_6h_break(
            staff_id, day, start, duration_slots, fixed=fixed
        ):
            continue
        out.append((day, start))
    return out


def _accumulate_booking_slot_coverage(
    model: cp_model.CpModel,
    booking,
    day: cp_model.IntVar,
    sd: cp_model.IntVar,
    dur: int,
    cover: dict[tuple[int, int, int], list[cp_model.IntVar]],
    entity_id: int,
) -> None:
    """Record optional slot coverage literals for one movable booking."""
    for d in range(NUM_DAYS):
        on_day = model.NewBoolVar(f"bkday_{booking.id}_{entity_id}_{d}")
        model.Add(day == d).OnlyEnforceIf(on_day)
        model.Add(day != d).OnlyEnforceIf(on_day.Not())
        for t in range(NUM_SLOTS):
            ge = model.NewBoolVar(f"bkge_{booking.id}_{entity_id}_{d}_{t}")
            lt = model.NewBoolVar(f"bklt_{booking.id}_{entity_id}_{d}_{t}")
            model.Add(sd <= t).OnlyEnforceIf(ge)
            model.Add(sd > t).OnlyEnforceIf(ge.Not())
            model.Add(t < sd + dur).OnlyEnforceIf(lt)
            model.Add(t >= sd + dur).OnlyEnforceIf(lt.Not())
            active = model.NewBoolVar(f"bkact_{booking.id}_{entity_id}_{d}_{t}")
            model.AddBoolAnd([on_day, ge, lt]).OnlyEnforceIf(active)
            model.AddBoolOr([on_day.Not(), ge.Not(), lt.Not()]).OnlyEnforceIf(active.Not())
            cover[(entity_id, d, t)].append(active)


def _finalize_teach_grid(
    model: cp_model.CpModel,
    teach: dict[tuple[int, int, int], cp_model.IntVar],
    cover: dict[tuple[int, int, int], list[cp_model.IntVar]],
    fixed_slots: set[tuple[int, int, int]],
) -> None:
    """``teach`` is 1 iff any booking covers that slot (fixed slots are already pinned to 1)."""
    for key, tv in teach.items():
        if key in fixed_slots:
            continue
        blocks = cover.get(key, [])
        if not blocks:
            model.Add(tv == 0)
        elif len(blocks) == 1:
            model.Add(tv == blocks[0])
        else:
            model.AddBoolOr(blocks).OnlyEnforceIf(tv)
            model.AddBoolAnd([b.Not() for b in blocks]).OnlyEnforceIf(tv.Not())


def _student_daily_hours_slack_violation(
    model: cp_model.CpModel,
    teach: dict[tuple[int, int, int], cp_model.IntVar],
    course_ids: list[int],
) -> cp_model.IntVar | None:
    """Minimize per-cohort teaching-day gap from the 5–8 hour ideal band."""
    slacks: list[cp_model.IntVar] = []
    for cid in course_ids:
        for d in range(NUM_DAYS):
            total = model.NewIntVar(0, NUM_SLOTS, f"stutot_{cid}_{d}")
            model.Add(total == sum(teach[(cid, d, t)] for t in range(NUM_SLOTS)))
            works = model.NewBoolVar(f"stuwrk_{cid}_{d}")
            model.Add(total >= 1).OnlyEnforceIf(works)
            model.Add(total == 0).OnlyEnforceIf(works.Not())
            under = model.NewIntVar(
                0, STUDENT_IDEAL_MIN_DAILY_TEACHING_SLOTS, f"stuund_{cid}_{d}"
            )
            model.Add(under >= STUDENT_IDEAL_MIN_DAILY_TEACHING_SLOTS - total).OnlyEnforceIf(
                works
            )
            model.Add(under == 0).OnlyEnforceIf(works.Not())
            slacks.append(under)
            over = model.NewIntVar(0, NUM_SLOTS, f"stuovr_{cid}_{d}")
            model.Add(over >= total - STUDENT_IDEAL_MAX_DAILY_TEACHING_SLOTS).OnlyEnforceIf(
                works
            )
            model.Add(over == 0).OnlyEnforceIf(works.Not())
            slacks.append(over)
    if not slacks:
        return None
    return _sum_violation_vars(model, slacks, "viol_student_daily")


def _student_daily_hours_slack_penalties(
    model: cp_model.CpModel,
    teach: dict[tuple[int, int, int], cp_model.IntVar],
    course_ids: list[int],
    penalty: int,
) -> list:
    total = _student_daily_hours_slack_violation(model, teach, course_ids)
    if total is None:
        return []
    return [penalty * total]


def _daily_hours_band_violations(
    model: cp_model.CpModel,
    teach: dict[tuple[int, int, int], cp_model.IntVar],
    entity_ids: list[int],
    prefix: str,
) -> list[cp_model.IntVar]:
    """Violation bools for teaching days outside 5–9 hours (per entity/day)."""
    viols: list[cp_model.IntVar] = []
    for eid in entity_ids:
        for d in range(NUM_DAYS):
            total = model.NewIntVar(0, NUM_SLOTS, f"{prefix}_tot_{eid}_{d}")
            model.Add(total == sum(teach[(eid, d, t)] for t in range(NUM_SLOTS)))
            works = model.NewBoolVar(f"{prefix}_wrk_{eid}_{d}")
            model.Add(total >= 1).OnlyEnforceIf(works)
            model.Add(total == 0).OnlyEnforceIf(works.Not())
            under = model.NewBoolVar(f"{prefix}_und_{eid}_{d}")
            model.Add(total < MIN_DAILY_TEACHING_SLOTS).OnlyEnforceIf(under)
            model.Add(total >= MIN_DAILY_TEACHING_SLOTS).OnlyEnforceIf(under.Not())
            over = model.NewBoolVar(f"{prefix}_ovr_{eid}_{d}")
            model.Add(total > MAX_DAILY_TEACHING_SLOTS).OnlyEnforceIf(over)
            model.Add(total <= MAX_DAILY_TEACHING_SLOTS).OnlyEnforceIf(over.Not())
            viol_under = model.NewBoolVar(f"{prefix}_vu_{eid}_{d}")
            model.Add(viol_under <= works)
            model.Add(viol_under <= under)
            model.Add(viol_under >= works + under - 1)
            viol_over = model.NewBoolVar(f"{prefix}_vo_{eid}_{d}")
            model.Add(viol_over <= works)
            model.Add(viol_over <= over)
            model.Add(viol_over >= works + over - 1)
            viols.append(viol_under)
            viols.append(viol_over)
    return viols


def _daily_hours_band_penalties(
    model: cp_model.CpModel,
    teach: dict[tuple[int, int, int], cp_model.IntVar],
    entity_ids: list[int],
    penalty: int,
    prefix: str,
) -> list:
    """Penalise days with teaching outside 5–9 hours (per entity/day)."""
    obj: list = []
    for viol in _daily_hours_band_violations(model, teach, entity_ids, prefix):
        obj.append(penalty * viol)
    return obj

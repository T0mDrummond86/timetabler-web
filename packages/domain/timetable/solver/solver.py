"""OR-Tools CP-SAT scheduler for the timetable.

Operates on a set of *movable* bookings and a set of *fixed* bookings:
  - Movable: solver chooses (day, start_slot, staff_id, room_id).
  - Fixed: kept as-is, but their resource usage is honoured by no-overlap.

Term-aware: each booking belongs to T1, T2, or both. Two bookings only
clash if they share a term, so no-overlap is enforced per-term per-resource.

Constraints enforced:
  - Each booking placed on (day, start) with its existing duration.
  - Per-staff, per-room, per-course no-overlap, per term (virtual rooms exempt).
  - Staff candidate = competent staff if any, else all (empty list = unconstrained).
  - Room candidate filtered by UnitAllowedRoom (if non-empty), required_room_type,
    and required_capacity.
  - Qualification time-window: booking's (day, start, end) must fit in one of
    each qualification's allowed windows.
  - Per-staff weekly hour cap (per term), optionally from FTE (Staff tab).

Optional ``staff_constraints`` (Auto-timetable tab):
  - Blocked times (strong) → placement must fit StaffAvailability windows.
  - Non-teaching day (medium) → soft penalty when assigned on that day.
  - Total teaching hours within ±2 h of FTE allocation (medium soft rule, per term).
  - Class preferences → soft penalties in the objective (1st / 2nd / 3rd).
  - Scheduling: 6h continuous teaching / 30min break between classes (strong), Friday 18:00 (strong),
    Monday start after 09:30 (medium), idle gaps over 2h (weak).

Objective: minimise drift, preference penalties, and soft scheduling penalties.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from ..constants import NUM_DAYS, NUM_SLOTS
from ..core.auto_timetable_constraints import (
    AutoTimetableConstraintSettings,
    StaffConstraintSettings,
    staff_preference_penalty,
    hard_blocked_slots_for_staff,
    valid_day_start_pairs,
)
from ..core.double_session import double_session_same_day
from ..core.qualification_schedule import (
    qual_day_start_pairs_for_duration,
    qual_day_start_pairs_for_same_day_double,
)
from ..core.scheduling_constraints import MIN_BREAK_SLOTS, filter_day_start_pairs
from .double_session_model import add_double_session_constraints, double_session_booking_pairs
from .staff_availability_model import non_teaching_day_penalty_terms
from .scheduling_model import (
    add_scheduling_constraints,
    filter_staff_day_start_pairs,
)
from ..core.booking_locks import (
    effective_lock_staff,
    effective_lock_time,
    pin_time_in_solver,
)
from ..core.room_types import room_type_is_online, room_types_match
from ..core.constraint_registry import (
    STEP_BLOCKED_TIMES,
    STEP_FTE_HOURS,
    STEP_NON_TEACHING_DAY,
    STEP_QUAL_WINDOWS,
    STRENGTH_STRONG,
    effective_strength,
)
from ..core.auto_timetable_constraints import non_teaching_day_slots
from ..core.models import (
    Booking,
    Course,
    QualificationTimeWindow,
    Room,
    Staff,
    StaffCompetency,
    Unit,
    UnitAllowedRoom,
)


WEEK_SLOTS = NUM_DAYS * NUM_SLOTS


@dataclass
class Assignment:
    booking_id: int
    day: int
    start_slot: int
    end_slot: int
    staff_id: int | None
    room_id: int | None


@dataclass(frozen=True)
class PinnedPlacement:
    """Fixed day/time/room from the placement phase (staff assigned later)."""
    day: int
    start_slot: int
    end_slot: int
    room_id: int | None


@dataclass
class SolveReport:
    status: str
    moves: list[Assignment]
    objective: int | None
    seconds: float
    relaxed_constraints: tuple[str, ...] = ()
    constraint_violations: dict[str, int] = field(default_factory=dict)
    solve_pass: str = "full"  # full | lexicographic | phased | failed
    failure_hints: tuple[str, ...] = ()
    solve_attempts: int = 1
    per_tier_cost: dict[str, int] = field(default_factory=dict)


def _terms(b: Booking) -> tuple[bool, bool]:
    return bool(getattr(b, "in_term_1", 1)), bool(getattr(b, "in_term_2", 1))


def _valid_placement(raw_abs: int, dur: int) -> tuple[int, int] | None:
    """Return (day, start_slot) when abs_start is a legal placement, else None."""
    week_slots = NUM_DAYS * NUM_SLOTS
    if not (0 <= raw_abs < week_slots):
        return None
    day = raw_abs // NUM_SLOTS
    sd = raw_abs % NUM_SLOTS
    if 0 <= day < NUM_DAYS and sd + dur <= NUM_SLOTS:
        return day, sd
    return None


def _build_moves_from_solution(
    *,
    solver: cp_model.CpSolver,
    movable: list[Booking],
    abs_starts: dict[int, cp_model.IntVar],
    durations: dict[int, int],
    staff_choice: dict[int, cp_model.IntVar],
    room_choice: dict[int, cp_model.IntVar],
    staff_allowed: dict[int, frozenset[int]],
    room_allowed: dict[int, frozenset[int]],
    auto_mode: bool,
) -> list[Assignment]:
    """Extract assignments only when every CP-SAT value is in-domain.

  If the solver reports FEASIBLE but returns garbage (e.g. after polish),
  return no moves so the UI never applies a corrupted timetable.
    """
    moves: list[Assignment] = []
    for b in movable:
        place = _valid_placement(solver.Value(abs_starts[b.id]), durations[b.id])
        if place is None:
            return []
        day, sd = place
        sid_val = solver.Value(staff_choice[b.id])
        rid_val = solver.Value(room_choice[b.id])
        allowed_s = staff_allowed[b.id]
        allowed_r = room_allowed[b.id]
        if auto_mode:
            if sid_val not in allowed_s or rid_val not in allowed_r:
                return []
            staff_id, room_id = sid_val, rid_val
        else:
            staff_id = sid_val if sid_val in allowed_s else None
            room_id = rid_val if rid_val in allowed_r else None
        moves.append(
            Assignment(
                booking_id=b.id,
                day=day,
                start_slot=sd,
                end_slot=sd + durations[b.id],
                staff_id=staff_id,
                room_id=room_id,
            )
        )
    return moves


def validate_proposed_assignments(
    session: Session,
    week_id: int,
    assignments: list[Assignment],
) -> tuple[bool, str]:
    """Check that applying ``assignments`` would not introduce staff/room clashes."""
    if not assignments:
        return True, ""
    week_bookings = (
        session.query(Booking).filter(Booking.week_id == week_id).all()
    )
    by_id = {b.id: b for b in week_bookings}
    proposed: dict[int, Assignment] = {a.booking_id: a for a in assignments}

    def slot_maps() -> tuple[dict, dict]:
        staff_map: dict[tuple[int, int, int], list[int]] = {}
        room_map: dict[tuple[int, int, int], list[int]] = {}
        for b in week_bookings:
            a = proposed.get(b.id)
            staff_id = a.staff_id if a and a.staff_id is not None else b.staff_id
            room_id = a.room_id if a and a.room_id is not None else b.room_id
            day = a.day if a else b.day
            start = a.start_slot if a else b.start_slot
            end = a.end_slot if a else b.end_slot
            for slot in range(start, end):
                if staff_id is not None:
                    key = (staff_id, day, slot)
                    staff_map.setdefault(key, []).append(b.id)
                if room_id is not None:
                    key = (room_id, day, slot)
                    room_map.setdefault(key, []).append(b.id)
        return staff_map, room_map

    staff_map, room_map = slot_maps()
    for key, bids in staff_map.items():
        if len(bids) > 1:
            return False, f"Lecturer double-booked after apply (staff {key[0]}, day {key[1]})."
    for key, bids in room_map.items():
        if len(bids) > 1:
            return False, f"Room double-booked after apply (room {key[0]}, day {key[1]})."
    return True, ""


class _CancelOnFlagCallback(cp_model.CpSolverSolutionCallback):
    def on_solution_callback(self) -> None:
        from .cancel_registry import solve_cancel_registry

        if solve_cancel_registry.stop_requested:
            self.StopSearch()


def _solve_with_cancel(solver: cp_model.CpSolver, model: cp_model.CpModel) -> int:
    from .cancel_registry import registered_solver, solve_cancel_registry

    if solve_cancel_registry.stop_requested:
        return cp_model.UNKNOWN
    callback = _CancelOnFlagCallback()
    with registered_solver(solver):
        return solver.Solve(model, callback)


def solve(
    session: Session,
    week_id: int,
    movable_ids: list[int] | None = None,
    *,
    time_limit_s: float = 15.0,
    staff_constraints: AutoTimetableConstraintSettings | StaffConstraintSettings | None = None,
    honor_qual_windows: bool = True,
    lexicographic_order: tuple[str, ...] | None = None,
    solve_phase: str | None = None,
    pinned_placement: dict[int, PinnedPlacement] | None = None,
) -> SolveReport:
    """Run the solver for one week.

    `movable_ids` defaults to all bookings in the week. Bookings not in this
    list are treated as fixed (their (day, start, staff, room) are pinned).
    """
    bookings: list[Booking] = (
        session.query(Booking)
        .filter(Booking.week_id == week_id, Booking.block_week_index.is_(None))
        .all()
    )
    staff_all = {s.id: s for s in session.query(Staff).all()}
    course_all = {c.id: c for c in session.query(Course).all()}
    if movable_ids is None:
        movable_ids = [b.id for b in bookings]
    movable_set = set(movable_ids)
    movable = [b for b in bookings if b.id in movable_set]
    fixed = [b for b in bookings if b.id not in movable_set]

    room_all = {r.id: r for r in session.query(Room).all()}
    unit_all = {u.id: u for u in session.query(Unit).all()}
    unit_by_name = {u.name.strip().lower(): u.id for u in unit_all.values() if u.name}
    sc = staff_constraints or AutoTimetableConstraintSettings()
    sched = sc.scheduling
    auto_mode = staff_constraints is not None
    phase = solve_phase or "full"
    defer_staff_no_overlap = phase == "placement"
    # Day/night qualification windows stay hard — never lexicographic soft compromises.
    lex_soft = frozenset(lexicographic_order or ()) - {STEP_QUAL_WINDOWS}
    use_lexicographic = auto_mode and bool(lexicographic_order)
    placement_pinned = pinned_placement or {}
    use_blocked_hard = sc.blocked_times and (
        not auto_mode
        or (
            effective_strength(sc, STEP_BLOCKED_TIMES) == STRENGTH_STRONG
            and STEP_BLOCKED_TIMES not in lex_soft
        )
    )
    blocked_by_staff: dict[int, set[tuple[int, int]] | None] = {}
    if use_blocked_hard:
        for sid, s in staff_all.items():
            blocked_by_staff[sid] = hard_blocked_slots_for_staff(s, session, sc) or set()
            if (
                sc.non_teaching_day
                and effective_strength(sc, STEP_NON_TEACHING_DAY) == STRENGTH_STRONG
                and STEP_NON_TEACHING_DAY not in lex_soft
            ):
                blocked_by_staff[sid] |= non_teaching_day_slots(s)
    elif use_lexicographic and (sc.blocked_times or sc.non_teaching_day):
        from .constraint_violations import prepare_blocked_by_staff

        blocked_by_staff = prepare_blocked_by_staff(
            staff_all, session, sc, lexicographic_soft=lex_soft
        )

    competencies: set[tuple[int, int]] = set(
        session.query(StaffCompetency.staff_id, StaffCompetency.unit_id).all()
    )
    # Per-unit allowed room set (empty set = no constraint).
    unit_allowed_rooms: dict[int, set[int]] = defaultdict(set)
    for unit_id, room_id in session.query(UnitAllowedRoom.unit_id, UnitAllowedRoom.room_id).all():
        unit_allowed_rooms[unit_id].add(room_id)
    # Qualification time windows are scoped to the booking's *course* (a
    # cohort belongs to one qualification), not to every qualification its
    # class happens to be associated with.
    course_qualification = {
        c.id: c.qualification_id
        for c in session.query(Course).all()
        if c.qualification_id is not None
    }
    if honor_qual_windows:
        from ..core.qualification_schedule import qual_windows_by_qualification_id

        qual_windows = qual_windows_by_qualification_id(session)
    else:
        qual_windows = defaultdict(list)
        for w in session.query(QualificationTimeWindow).all():
            qual_windows[w.qualification_id].append((w.day, w.start_slot, w.end_slot))

    model = cp_model.CpModel()

    abs_starts: dict[int, cp_model.IntVar] = {}
    durations: dict[int, int] = {}
    course_intervals: dict[int, dict[str, cp_model.IntervalVar]] = {}
    staff_choice: dict[int, cp_model.IntVar] = {}
    room_choice: dict[int, cp_model.IntVar] = {}
    staff_allowed: dict[int, frozenset[int]] = {}
    room_allowed: dict[int, frozenset[int]] = {}
    staff_presence: dict[int, dict[int | None, cp_model.IntVar]] = {}
    staff_intervals: dict[int, list[tuple[int | None, cp_model.IntervalVar]]] = {}
    room_intervals: dict[int, list[tuple[int | None, cp_model.IntervalVar]]] = {}
    day_var: dict[int, cp_model.IntVar] = {}
    start_var: dict[int, cp_model.IntVar] = {}

    movable_ids_set = {b.id for b in movable}
    same_day_double_part1: dict[int, tuple[int, int]] = {}
    skip_qual_booking_ids: set[int] = set()
    for b1, b2 in double_session_booking_pairs(movable, unit_all):
        unit = unit_all.get(b1.unit_id)
        if unit is None or not double_session_same_day(unit):
            continue
        d1 = b1.end_slot - b1.start_slot
        d2 = b2.end_slot - b2.start_slot
        if b1.id in movable_ids_set:
            same_day_double_part1[b1.id] = (b2.id, d2)
            if b2.id in movable_ids_set:
                skip_qual_booking_ids.add(b2.id)

    for b in movable:
        dur = b.end_slot - b.start_slot
        durations[b.id] = dur
        day = model.NewIntVar(0, NUM_DAYS - 1, f"day_{b.id}")
        sd = model.NewIntVar(0, NUM_SLOTS - dur, f"sd_{b.id}")
        abs_start = model.NewIntVar(0, WEEK_SLOTS - dur, f"abs_{b.id}")
        model.Add(abs_start == day * NUM_SLOTS + sd)
        abs_starts[b.id] = abs_start
        day_var[b.id] = day
        start_var[b.id] = sd

        # Per-term course intervals — used in the per-term no-overlap pools.
        t1, t2 = _terms(b)
        course_intervals[b.id] = {}
        if t1:
            course_intervals[b.id]["t1"] = model.NewIntervalVar(
                abs_start, dur, abs_start + dur, f"crs_t1_{b.id}"
            )
        if t2:
            course_intervals[b.id]["t2"] = model.NewIntervalVar(
                abs_start, dur, abs_start + dur, f"crs_t2_{b.id}"
            )

        # Staff candidates.
        staff_candidates: list[int | None] = [None]
        if b.unit_id is not None:
            elig = [sid for sid in staff_all if (sid, b.unit_id) in competencies]
            staff_candidates += elig if elig else list(staff_all.keys())
        else:
            staff_candidates += list(staff_all.keys())
        staff_candidates = list(dict.fromkeys(staff_candidates))
        st = staff_all.get(b.staff_id) if b.staff_id is not None else None
        co = course_all.get(b.course_id) if b.course_id is not None else None
        if pin_time_in_solver(b, staff=st, course=co):
            model.Add(day == b.day)
            model.Add(sd == b.start_slot)
        if effective_lock_staff(b, staff=st, course=co) and b.staff_id is not None:
            if b.staff_id in staff_candidates:
                staff_candidates = [b.staff_id]
        if use_blocked_hard and not lex_soft:
            staff_candidates = [
                sid
                for sid in staff_candidates
                if sid is None
                or valid_day_start_pairs(dur, blocked_by_staff.get(sid))
            ]

        # Room candidates: filtered by allowed-room list (if any), then by
        # legacy required_room_type / required_capacity.
        room_candidates: list[int | None] = [None]
        u = unit_all.get(b.unit_id) if b.unit_id else None
        allowed = unit_allowed_rooms.get(b.unit_id or -1)
        for rid, r in room_all.items():
            if allowed and rid not in allowed:
                continue
            if u and u.required_room_type and not room_types_match(
                u.required_room_type, r.room_type
            ):
                continue
            if u and u.required_capacity and (r.capacity or 0) < u.required_capacity:
                continue
            room_candidates.append(rid)

        # Auto-timetable must assign a lecturer and room when any candidate exists.
        if auto_mode:
            staff_only = [x for x in staff_candidates if x is not None]
            if staff_only:
                staff_candidates = staff_only
            elif staff_all:
                staff_candidates = list(staff_all.keys())
            rooms_only = [x for x in room_candidates if x is not None]
            if rooms_only:
                room_candidates = rooms_only
            elif room_all:
                room_candidates = list(room_all.keys())

        if not staff_candidates:
            staff_candidates = [None]
        if not room_candidates:
            room_candidates = [None]

        s_choice = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues([-1 if x is None else x for x in staff_candidates]),
            f"sch_{b.id}",
        )
        r_choice = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues([-1 if x is None else x for x in room_candidates]),
            f"rch_{b.id}",
        )
        staff_choice[b.id] = s_choice
        room_choice[b.id] = r_choice
        staff_allowed[b.id] = frozenset(
            x for x in staff_candidates if x is not None
        )
        room_allowed[b.id] = frozenset(
            x for x in room_candidates if x is not None
        )

        pin = placement_pinned.get(b.id)
        if pin is not None:
            model.Add(day == pin.day)
            model.Add(sd == pin.start_slot)
            if pin.room_id is not None and pin.room_id in room_allowed[b.id]:
                model.Add(r_choice == pin.room_id)

        sp: dict[int | None, cp_model.IntVar] = {}
        si: list[tuple[int | None, cp_model.IntervalVar]] = []
        for sid in staff_candidates:
            pres = model.NewBoolVar(f"sp_{b.id}_{sid}")
            sp[sid] = pres
            sentinel = -1 if sid is None else sid
            model.Add(s_choice == sentinel).OnlyEnforceIf(pres)
            model.Add(s_choice != sentinel).OnlyEnforceIf(pres.Not())
            iv = model.NewOptionalIntervalVar(
                abs_start, dur, abs_start + dur, pres, f"siv_{b.id}_{sid}"
            )
            si.append((sid, iv))
        model.Add(sum(sp.values()) == 1)
        staff_presence[b.id] = sp
        staff_intervals[b.id] = si

        if use_blocked_hard:
            for sid in staff_candidates:
                if sid is None:
                    continue
                valid_pairs = valid_day_start_pairs(dur, blocked_by_staff.get(sid))
                if auto_mode:
                    valid_pairs = filter_staff_day_start_pairs(
                        valid_pairs,
                        dur,
                        sid,
                        fixed,
                        sched,
                        auto_settings=sc,
                        lexicographic_soft=lex_soft if use_lexicographic else None,
                    )
                if not valid_pairs:
                    model.Add(sp[sid] == 0)
                else:
                    model.AddAllowedAssignments([day, sd], valid_pairs).OnlyEnforceIf(sp[sid])

        rp: dict[int | None, cp_model.IntVar] = {}
        ri: list[tuple[int | None, cp_model.IntervalVar]] = []
        for rid in room_candidates:
            pres = model.NewBoolVar(f"rp_{b.id}_{rid}")
            rp[rid] = pres
            sentinel = -1 if rid is None else rid
            model.Add(r_choice == sentinel).OnlyEnforceIf(pres)
            model.Add(r_choice != sentinel).OnlyEnforceIf(pres.Not())
            iv = model.NewOptionalIntervalVar(
                abs_start, dur, abs_start + dur, pres, f"riv_{b.id}_{rid}"
            )
            ri.append((rid, iv))
        model.Add(sum(rp.values()) == 1)
        room_intervals[b.id] = ri

        if auto_mode:
            if any(sid is not None for sid in staff_candidates):
                model.Add(s_choice != -1)
            if any(rid is not None for rid in room_candidates):
                model.Add(r_choice != -1)

        # --- Qualification time windows (scoped to the booking's course) ---
        qid = course_qualification.get(b.course_id)
        if honor_qual_windows and qid is not None and b.id not in skip_qual_booking_ids:
            windows = qual_windows.get(qid)
            if windows:
                if b.id in same_day_double_part1:
                    _, d2 = same_day_double_part1[b.id]
                    qual_pairs = qual_day_start_pairs_for_same_day_double(
                        dur, MIN_BREAK_SLOTS, d2, windows
                    )
                else:
                    qual_pairs = qual_day_start_pairs_for_duration(dur, windows)
                if qual_pairs:
                    model.AddAllowedAssignments([day, sd], qual_pairs)
                else:
                    # Class longer than the day/night window — do not leave placement unconstrained.
                    model.Add(day == NUM_DAYS)
            elif auto_mode and sched.friday_finish_by_6pm:
                all_pairs = [
                    (d, s)
                    for d in range(NUM_DAYS)
                    for s in range(NUM_SLOTS - dur + 1)
                ]
                filtered = filter_day_start_pairs(all_pairs, dur, sched)
                if filtered:
                    model.AddAllowedAssignments([day, sd], filtered)

    # ---- No-overlap pools, split by term ----
    staff_pool: dict[tuple[int, str], list[cp_model.IntervalVar]] = defaultdict(list)
    room_pool: dict[tuple[int, str], list[cp_model.IntervalVar]] = defaultdict(list)
    course_pool: dict[tuple[int, str], list[cp_model.IntervalVar]] = defaultdict(list)

    for b in movable:
        t1, t2 = _terms(b)
        terms_active = (("t1",) if t1 else ()) + (("t2",) if t2 else ())
        for sid, iv in staff_intervals[b.id]:
            if sid is None:
                continue
            for term in terms_active:
                if defer_staff_no_overlap:
                    staff_pool[("placement", b.id, term)].append(iv)
                else:
                    staff_pool[(sid, term)].append(iv)
        for rid, iv in room_intervals[b.id]:
            if rid is None:
                continue
            if room_type_is_online(room_all[rid].room_type):
                continue
            for term in terms_active:
                room_pool[(rid, term)].append(iv)
        for term in terms_active:
            ci = course_intervals[b.id].get(term)
            if ci is not None:
                course_pool[(b.course_id, term)].append(ci)

    for b in fixed:
        abs_s = b.day * NUM_SLOTS + b.start_slot
        dur = b.end_slot - b.start_slot
        if dur <= 0:
            continue
        t1, t2 = _terms(b)
        terms_active = (("t1",) if t1 else ()) + (("t2",) if t2 else ())
        for term in terms_active:
            if b.staff_id is not None:
                staff_pool[(b.staff_id, term)].append(
                    model.NewIntervalVar(abs_s, dur, abs_s + dur, f"fxs_{b.id}_{term}")
                )
            if (
                b.room_id is not None
                and b.room_id in room_all
                and not room_type_is_online(room_all[b.room_id].room_type)
            ):
                room_pool[(b.room_id, term)].append(
                    model.NewIntervalVar(abs_s, dur, abs_s + dur, f"fxr_{b.id}_{term}")
                )
            course_pool[(b.course_id, term)].append(
                model.NewIntervalVar(abs_s, dur, abs_s + dur, f"fxc_{b.id}_{term}")
            )

    for ivs in staff_pool.values():
        if len(ivs) > 1:
            model.AddNoOverlap(ivs)
    for ivs in room_pool.values():
        if len(ivs) > 1:
            model.AddNoOverlap(ivs)
    for ivs in course_pool.values():
        if len(ivs) > 1:
            model.AddNoOverlap(ivs)

    # Legacy per-staff max_hours_per_week cap (hard) when set on the staff record.
    for sid, s in staff_all.items():
        if s.max_hours_per_week is None:
            continue
        cap_slots = int(s.max_hours_per_week * 2)
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
            if fixed_load > cap_slots:
                continue
            terms_terms = []
            for b in movable:
                t1, t2 = _terms(b)
                if (term == "t1" and not t1) or (term == "t2" and not t2):
                    continue
                if sid in staff_presence.get(b.id, {}):
                    terms_terms.append(staff_presence[b.id][sid] * durations[b.id])
            if terms_terms:
                model.Add(sum(terms_terms) + fixed_load <= cap_slots)

    if auto_mode:
        add_double_session_constraints(
            model,
            bookings=movable + fixed,
            unit_all=unit_all,
            staff_choice=staff_choice,
            room_choice=room_choice,
            day_var=day_var,
            start_var=start_var,
            durations=durations,
        )

    scheduling_obj: list = []
    sched_lex_violations: dict[str, cp_model.IntVar] = {}
    if auto_mode:
        scheduling_obj, sched_lex_violations = add_scheduling_constraints(
            model,
            movable=movable,
            fixed=fixed,
            staff_all=staff_all,
            staff_presence=staff_presence,
            day_var=day_var,
            start_var=start_var,
            durations=durations,
            settings=sched,
            auto_settings=sc,
            lexicographic_soft=lex_soft if use_lexicographic else None,
            lexicographic_mode=use_lexicographic,
        )

    nt_penalty_terms: list = []
    if (
        auto_mode
        and sc.non_teaching_day
        and effective_strength(sc, STEP_NON_TEACHING_DAY) != STRENGTH_STRONG
        and STEP_NON_TEACHING_DAY not in lex_soft
    ):
        nt_penalty_terms = non_teaching_day_penalty_terms(
            model,
            movable=movable,
            staff_all=staff_all,
            staff_presence=staff_presence,
            day_var=day_var,
        )

    # ---- Objective: minimise drift + preference penalties ----
    drift_terms = []
    pref_terms = []
    prefs_enabled = (
        sc.first_preferences or sc.second_preferences or sc.third_preferences
    )
    for b in movable:
        if phase != "staff":
            cur_abs = b.day * NUM_SLOTS + b.start_slot
            diff = model.NewIntVar(0, WEEK_SLOTS, f"drift_{b.id}")
            signed = model.NewIntVar(-WEEK_SLOTS, WEEK_SLOTS, f"sd_{b.id}")
            model.Add(signed == abs_starts[b.id] - cur_abs)
            model.AddAbsEquality(diff, signed)
            drift_terms.append(diff)
        if phase == "placement":
            continue
        if prefs_enabled and b.unit_id is not None:
            for sid, pres in staff_presence[b.id].items():
                if sid is None:
                    continue
                pen = staff_preference_penalty(
                    sid,
                    b.unit_id,
                    session=session,
                    settings=sc,
                    unit_by_name=unit_by_name,
                )
                if pen > 0:
                    pref_terms.append(pen * pres)
    polish_terms = drift_terms + pref_terms + nt_penalty_terms
    if not use_lexicographic:
        polish_terms = polish_terms + scheduling_obj
    violation_locked: dict[str, int] = {}

    solver = cp_model.CpSolver()
    if use_lexicographic and lexicographic_order:
        from .constraint_violations import build_pipeline_violations
        from .lexicographic_solve import run_lexicographic, violation_report_lines

        order = tuple(sid for sid in lexicographic_order if sid != STEP_QUAL_WINDOWS)
        pipeline_violations = build_pipeline_violations(
            model,
            order=order,
            sc=sc,
            movable=movable,
            fixed=fixed,
            staff_all=staff_all,
            staff_presence=staff_presence,
            day_var=day_var,
            start_var=start_var,
            durations=durations,
            blocked_by_staff=blocked_by_staff,
            course_qualification=course_qualification,
            qual_windows=qual_windows,
            terms_fn=_terms,
            scheduling_violations=sched_lex_violations,
        )
        status, violation_locked = run_lexicographic(
            model,
            solver,
            violation_vars=pipeline_violations,
            order=order,
            polish_terms=polish_terms,
            time_limit_s=time_limit_s,
            settings=sc,
            n_bookings=len(movable),
        )
        relaxed_labels = violation_report_lines(violation_locked, settings=sc)
    else:
        if polish_terms:
            model.Minimize(sum(polish_terms))
        solver.parameters.max_time_in_seconds = time_limit_s
        if auto_mode:
            solver.parameters.num_search_workers = 1
        status = _solve_with_cancel(solver, model)
        relaxed_labels = ()

    status_name = solver.StatusName(status)

    moves: list[Assignment] = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        moves = _build_moves_from_solution(
            solver=solver,
            movable=movable,
            abs_starts=abs_starts,
            durations=durations,
            staff_choice=staff_choice,
            room_choice=room_choice,
            staff_allowed=staff_allowed,
            room_allowed=room_allowed,
            auto_mode=auto_mode,
        )
        if not moves and movable:
            status_name = "UNKNOWN"
    corrupt_hint: tuple[str, ...] = ()
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) and not moves and movable:
        corrupt_hint = (
            "The solver finished but produced invalid placements (corrupted values). "
            "Nothing was applied — try again or relax constraints.",
        )
    solve_pass = "full"
    if use_lexicographic:
        solve_pass = "lexicographic" if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else "failed"

    return SolveReport(
        status=status_name,
        moves=moves,
        objective=int(solver.ObjectiveValue()) if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None,
        seconds=solver.WallTime(),
        relaxed_constraints=relaxed_labels,
        constraint_violations=dict(violation_locked),
        solve_pass=solve_pass,
        failure_hints=corrupt_hint,
    )


def apply_assignments(session: Session, assignments: list[Assignment]) -> None:
    """Persist a solver result back to the bookings."""
    if assignments:
        week_id = session.get(Booking, assignments[0].booking_id)
        if week_id is not None:
            ok, reason = validate_proposed_assignments(
                session, week_id.week_id, assignments
            )
            if not ok:
                raise ValueError(reason or "Proposed timetable has clashes.")
    staff_all = {s.id: s for s in session.query(Staff).all()}
    room_all = {r.id: r for r in session.query(Room).all()}
    course_all = {c.id: c for c in session.query(Course).all()}
    affected: list[Booking] = []
    for a in assignments:
        b = session.get(Booking, a.booking_id)
        if b is None:
            continue
        st = staff_all.get(b.staff_id) if b.staff_id is not None else None
        co = course_all.get(b.course_id) if b.course_id is not None else None
        if not effective_lock_time(b, staff=st, course=co):
            b.day = a.day
            b.start_slot = a.start_slot
            b.end_slot = a.end_slot
        if not (effective_lock_staff(b, staff=st, course=co) and b.staff_id is not None):
            if a.staff_id is not None and a.staff_id in staff_all:
                b.staff_id = a.staff_id
        if a.room_id is not None and a.room_id in room_all:
            b.room_id = a.room_id
        affected.append(b)
    session.commit()
    for b in affected:
        session.expire(b, ["staff", "room"])

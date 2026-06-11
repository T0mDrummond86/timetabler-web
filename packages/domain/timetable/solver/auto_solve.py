"""Auto-timetable: phased CP-SAT (placement then lecturers) with relaxed lex rules."""
from __future__ import annotations

import copy
import logging
import time
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.storage import app_data_dir
from ..constants import NUM_DAYS, NUM_SLOTS
from ..core.auto_timetable_constraints import AutoTimetableConstraintSettings
from ..core.constraint_registry import placement_lex_order, staff_lex_order
from ..core.models import (
    Booking,
    Course,
    Room,
    Staff,
    Unit,
    UnitAllowedRoom,
)
from ..core.qualification_schedule import qual_windows_by_qualification_id
from ..core.room_types import room_types_match
from ..core.staff_competency import unit_has_unsatisfiable_lecturer_constraint
from ..core.scheduling_constraints import (
    SchedulingConstraintSettings,
    filter_day_start_pairs,
)
from .solver import Assignment, PinnedPlacement, SolveReport, solve, validate_proposed_assignments

_LOG_PATH = app_data_dir() / "auto_solve_diag.log"


def _log(phase: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {phase}\n"
    logging.getLogger("timetable.auto_solve").debug(phase)
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def time_limit_for_booking_count(
    n_bookings: int,
    settings: AutoTimetableConstraintSettings | None = None,
) -> float:
    """Wall-clock budget for phased auto-solve (seconds)."""
    if n_bookings <= 0:
        return 45.0
    limit = min(240.0, max(90.0, 60.0 + n_bookings * 0.5))
    if settings is not None and settings.scheduling.student_daily_hours_5_to_9:
        limit = min(360.0, max(limit, 180.0 + n_bookings * 0.45))
    return limit


def _is_feasible(rep: SolveReport) -> bool:
    return rep.status in ("OPTIMAL", "FEASIBLE") and bool(rep.moves)


def _core_settings(settings: AutoTimetableConstraintSettings) -> AutoTimetableConstraintSettings:
    """Alias for placement-phase settings (tests and direct solve calls)."""
    return _placement_settings(settings)


def _placement_settings(
    settings: AutoTimetableConstraintSettings,
) -> AutoTimetableConstraintSettings:
    """Phase 1: cohort days + rooms only; lecturers deferred."""
    s = copy.deepcopy(settings)
    user_sched = settings.scheduling
    s.scheduling = SchedulingConstraintSettings(
        break_every_6_hours=False,
        friday_finish_by_6pm=False,
        monday_start_after_930=False,
        student_daily_hours_5_to_9=user_sched.student_daily_hours_5_to_9,
        student_break_max_2_hours=False,
        max_idle_gap_2_hours=False,
        staff_daily_hours_5_to_9=False,
    )
    s.total_hours_match_fte = False
    s.blocked_times = False
    s.non_teaching_day = False
    s.first_preferences = False
    s.second_preferences = False
    s.third_preferences = False
    return s


def _staff_phase_settings(
    settings: AutoTimetableConstraintSettings,
) -> AutoTimetableConstraintSettings:
    """Phase 2: lecturer rules from user settings; scheduling on cohort days is fixed."""
    s = copy.deepcopy(settings)
    user_sched = settings.scheduling
    s.scheduling = SchedulingConstraintSettings(
        break_every_6_hours=user_sched.break_every_6_hours,
        friday_finish_by_6pm=False,
        monday_start_after_930=False,
        student_daily_hours_5_to_9=False,
        student_break_max_2_hours=False,
        max_idle_gap_2_hours=user_sched.max_idle_gap_2_hours,
        staff_daily_hours_5_to_9=False,
    )
    return s


def _bare_settings(settings: AutoTimetableConstraintSettings) -> AutoTimetableConstraintSettings:
    s = _placement_settings(settings)
    s.scheduling = SchedulingConstraintSettings(
        student_daily_hours_5_to_9=False,
    )
    return s


def _merge_moves(
    placement: list[Assignment], staff: list[Assignment]
) -> list[Assignment]:
    by_id = {m.booking_id: m for m in placement}
    for sm in staff:
        base = by_id.get(sm.booking_id)
        if base is None:
            by_id[sm.booking_id] = sm
        else:
            by_id[sm.booking_id] = Assignment(
                booking_id=base.booking_id,
                day=base.day,
                start_slot=base.start_slot,
                end_slot=base.end_slot,
                room_id=base.room_id,
                staff_id=sm.staff_id,
            )
    return list(by_id.values())


def _movable_bookings(
    session: Session, week_id: int, movable_ids: list[int] | None
) -> list[Booking]:
    q = session.query(Booking).filter(Booking.week_id == week_id)
    if movable_ids is not None:
        q = q.filter(Booking.id.in_(movable_ids))
    return q.all()


def placement_diagnostics(
    session: Session,
    week_id: int,
    movable_ids: list[int] | None,
) -> tuple[str, ...]:
    """Pre-flight hints (read-only; no database writes)."""
    hints: list[str] = []
    if session.query(Staff).count() == 0:
        hints.append("No lecturers in the Staff tab — add staff before auto-timetabling.")
    if session.query(Room).count() == 0:
        hints.append("No rooms in the Rooms tab.")

    staff_all = {s.id for s in session.query(Staff).all()}
    room_all = {r.id: r for r in session.query(Room).all()}
    unit_all = {u.id: u for u in session.query(Unit).all()}
    unit_allowed_rooms: dict[int, set[int]] = defaultdict(set)
    for unit_id, room_id in session.query(
        UnitAllowedRoom.unit_id, UnitAllowedRoom.room_id
    ).all():
        unit_allowed_rooms[unit_id].add(room_id)
    course_qual = {
        c.id: c.qualification_id
        for c in session.query(Course).all()
        if c.qualification_id is not None
    }
    qual_windows = qual_windows_by_qualification_id(session)

    sched = SchedulingConstraintSettings(friday_finish_by_6pm=True)
    no_staff = 0
    no_room = 0
    no_qual_slot = 0
    movable = _movable_bookings(session, week_id, movable_ids)
    n_movable = len(movable)

    for b in movable:
        dur = max(1, b.end_slot - b.start_slot)
        if b.unit_id is not None and staff_all:
            if unit_has_unsatisfiable_lecturer_constraint(
                session, b.unit_id, staff_ids=staff_all
            ):
                no_staff += 1
        u = unit_all.get(b.unit_id) if b.unit_id else None
        room_ok = False
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
            room_ok = True
            break
        if room_all and not room_ok:
            no_room += 1
        qid = course_qual.get(b.course_id)
        if qid is not None:
            windows = qual_windows.get(qid)
            if windows:
                valid = [
                    (d, s)
                    for d in range(NUM_DAYS)
                    for s in range(NUM_SLOTS - dur + 1)
                    if any(
                        wd == d and ws <= s and we >= s + dur
                        for (wd, ws, we) in windows
                    )
                ]
                valid = filter_day_start_pairs(valid, dur, sched)
                if not valid:
                    no_qual_slot += 1

    if no_staff:
        hints.append(
            f"{no_staff} of {n_movable} class(es) list allowed lecturers on the Classes tab "
            "who are not in the Staff tab (fix ticked names or add staff)."
        )
    if no_room:
        hints.append(
            f"{no_room} of {n_movable} class(es) have no room that matches allowed rooms, type, or capacity."
        )
    if no_qual_slot:
        hints.append(
            f"{no_qual_slot} of {n_movable} class(es) cannot fit in their qualification day/night windows "
            "(Qualifications tab → day/night period)."
        )
    return tuple(hints)


blocking_placement_issues = placement_diagnostics


def _preflight_blocks_solve(hints: tuple[str, ...], n_bookings: int) -> bool:
    """Return True only when solving cannot possibly start."""
    if n_bookings <= 0:
        return False
    for h in hints:
        if "No lecturers" in h or "No rooms" in h:
            return True
    return False


def solve_auto_timetable(
    session: Session,
    week_id: int,
    movable_ids: list[int] | None,
    settings: AutoTimetableConstraintSettings,
    *,
    time_limit_s: float | None = None,
) -> SolveReport:
    """Place classes in two phases: time/room/cohort days, then lecturers."""
    from ..core.models import Booking as BookingModel

    _log("solve_auto_timetable: start (phased)")
    if movable_ids is not None:
        n = len(movable_ids)
    else:
        n = session.query(BookingModel).filter(BookingModel.week_id == week_id).count()
    limit = time_limit_s if time_limit_s is not None else time_limit_for_booking_count(n, settings)
    _log(f"bookings={n} time_limit={limit:.0f}s")

    if n <= 0:
        _log("no bookings to schedule")
        return SolveReport(
            status="INFEASIBLE",
            moves=[],
            objective=None,
            seconds=0.0,
            solve_pass="failed",
            failure_hints=("There are no classes on the timetable to schedule.",),
        )

    _log("placement_diagnostics")
    preflight = placement_diagnostics(session, week_id, movable_ids)
    if preflight:
        _log(f"preflight: {preflight[0]}")

    if _preflight_blocks_solve(preflight, n):
        _log("preflight blocked — skipping CP-SAT")
        return SolveReport(
            status="INFEASIBLE",
            moves=[],
            objective=None,
            seconds=0.0,
            solve_pass="failed",
            failure_hints=preflight
            or ("Nothing to schedule.",),
        )

    placement_cfg = _placement_settings(settings)
    staff_cfg = _staff_phase_settings(settings)
    t_placement = limit * 0.58
    t_staff = limit * 0.42
    placement_order = placement_lex_order(placement_cfg)
    staff_order = staff_lex_order(staff_cfg)

    _log(
        f"phase 1 placement lex_steps={len(placement_order)} limit={t_placement:.0f}s"
    )
    t0 = time.monotonic()
    rep_place = solve(
        session,
        week_id,
        movable_ids=movable_ids,
        time_limit_s=t_placement,
        staff_constraints=placement_cfg,
        honor_qual_windows=True,
        lexicographic_order=placement_order or None,
        solve_phase="placement",
    )
    _log(
        f"phase 1 done status={rep_place.status} moves={len(rep_place.moves)} "
        f"wall={time.monotonic() - t0:.1f}s"
    )

    if not _is_feasible(rep_place):
        bare_limit = min(30.0, limit * 0.3)
        _log(f"bare CP-SAT pass limit={bare_limit:.0f}s")
        rep2 = solve(
            session,
            week_id,
            movable_ids=movable_ids,
            time_limit_s=bare_limit,
            staff_constraints=_bare_settings(settings),
            honor_qual_windows=False,
            lexicographic_order=None,
        )
        _log(f"bare done status={rep2.status}")
        if _is_feasible(rep2):
            rep2.solve_pass = "bare"
            rep2.relaxed_constraints = (
                "Minimal placement only — qualification windows and most rules were skipped.",
            )
            return rep2
        rep2.solve_pass = "failed"
        rep2.failure_hints = preflight or (
            "No valid placement exists with the current staff, rooms, and qualification windows.",
        )
        return rep2

    pinned = {
        m.booking_id: PinnedPlacement(
            day=m.day,
            start_slot=m.start_slot,
            end_slot=m.end_slot,
            room_id=m.room_id,
        )
        for m in rep_place.moves
    }

    _log(f"phase 2 staff lex_steps={len(staff_order)} limit={t_staff:.0f}s")
    t0 = time.monotonic()
    rep_staff = solve(
        session,
        week_id,
        movable_ids=movable_ids,
        time_limit_s=t_staff,
        staff_constraints=staff_cfg,
        honor_qual_windows=True,
        lexicographic_order=staff_order or None,
        solve_phase="staff",
        pinned_placement=pinned,
    )
    _log(
        f"phase 2 done status={rep_staff.status} moves={len(rep_staff.moves)} "
        f"wall={time.monotonic() - t0:.1f}s"
    )

    staff_note: tuple[str, ...] = ()
    if _is_feasible(rep_staff):
        moves = _merge_moves(rep_place.moves, rep_staff.moves)
    else:
        moves = rep_place.moves
        staff_note = (
            "Lecturer assignment phase ran out of time — day, time, and rooms were kept; "
            "assign lecturers manually or run again.",
        )
    else_note = staff_note

    ok, clash_msg = validate_proposed_assignments(session, week_id, moves)
    if not ok:
        _log(f"merged moves rejected: {clash_msg}")
        return SolveReport(
            status="INFEASIBLE",
            moves=[],
            objective=None,
            seconds=rep_place.seconds + getattr(rep_staff, "seconds", 0),
            solve_pass="failed",
            failure_hints=(clash_msg,) + else_note,
        )

    from .lexicographic_solve import violation_report_lines

    violations = dict(rep_place.constraint_violations)
    violations.update(rep_staff.constraint_violations)
    notes = violation_report_lines(violations, settings=staff_cfg)
    if else_note:
        notes = else_note + notes

    total_seconds = rep_place.seconds + (
        rep_staff.seconds if _is_feasible(rep_staff) else 0.0
    )
    return SolveReport(
        status=rep_place.status,
        moves=moves,
        objective=rep_staff.objective if _is_feasible(rep_staff) else rep_place.objective,
        seconds=total_seconds,
        relaxed_constraints=notes,
        constraint_violations=violations,
        solve_pass="phased",
    )


def format_apply_summary(
    rep: SolveReport, settings: AutoTimetableConstraintSettings
) -> str:
    lines = [
        f"Status: {rep.status} in {rep.seconds:.1f}s",
        f"Bookings to update: {len(rep.moves)}",
    ]
    if rep.solve_pass == "bare":
        lines.append("Pass: minimal placement (core rules could not be satisfied in time).")
    elif rep.solve_pass == "phased":
        lines.append(
            "Pass: phase 1 — day/time, rooms, and student cohort hours; "
            "phase 2 — lecturers (FTE, blocked times, gaps, preferences)."
        )
    elif rep.solve_pass == "lexicographic":
        lines.append(
            "Pass: qualification windows, staff rules, FTE load balancing, student daily hours "
            "(5–8 h ideal), and lecturer preferences (lexicographic)."
        )
    elif rep.solve_pass == "full":
        lines.append(
            "Pass: day/night qualification windows, staff rules, and lecturer preferences."
        )
    elif rep.solve_pass == "failed":
        lines.append("Pass: failed — no timetable was produced.")

    if rep.relaxed_constraints:
        for msg in rep.relaxed_constraints:
            lines.append(f"Note: {msg}")

    if rep.objective is not None and rep.objective > 0:
        lines.append(f"Preference penalty total: {rep.objective}")
    return "\n".join(lines)

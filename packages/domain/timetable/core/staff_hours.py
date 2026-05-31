"""Staff timetabled hours: FTE lecturing load, in-class vs online split, spreadsheet-style totals."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session, joinedload

from ..constants import SLOT_MINUTES
from .booking_sessions import (
    TERM1_WEEK_RANGE,
    TERM2_WEEK_RANGE,
    active_session_weeks_in_term,
    format_session_avg_line,
    is_full_session_schedule,
)
from .models import (
    Booking,
    Qualification,
    Room,
    Staff,
    StaffQualificationOnlineStudents,
    StaffUnitOnlineStudents,
    Unit,
    UnitQualification,
)

HOURS_PER_FTE = 21.0
DEFAULT_ONLINE_STUDENTS = 20
# Combined cohort (all parallel online lots for one class). Up to this count, lecturing
# load is one session's scheduled (in-class) hours; above it, the scaled formula applies.
ONLINE_COMBINED_STUDENTS_IN_CLASS_MAX = 34
# Divisor in: assigned_hours = (combined / divisor) * 1.5 * (one session's scheduled hours).
ONLINE_COMBINED_STUDENTS_FORMULA_DIVISOR = 50

VARIANCE_CATEGORY_ON_TARGET = "on_target"
VARIANCE_CATEGORY_FULL_FTE_OVERTIME = "full_fte_overtime"
VARIANCE_CATEGORY_FULL_FTE_SHORTFALL = "full_fte_shortfall"
VARIANCE_CATEGORY_PART_FTE_VARIATION = "part_fte_variation"
VARIANCE_CATEGORY_PART_FTE_VARIATION_OVERTIME = "part_fte_variation_overtime"
VARIANCE_CATEGORY_UNKNOWN = "unknown"


def classify_staff_variance(
    *,
    fte: float | None,
    lecturing_hours: float | None,
    total_hours: float,
    tolerance: float = 1e-6,
) -> str:
    """Classify a lecturer row for variance shading and filtering."""
    if lecturing_hours is None or fte is None:
        return VARIANCE_CATEGORY_UNKNOWN
    variance = total_hours - lecturing_hours
    if abs(variance) <= tolerance:
        return VARIANCE_CATEGORY_ON_TARGET
    if float(fte) >= 1.0:
        if variance > 0:
            return VARIANCE_CATEGORY_FULL_FTE_OVERTIME
        return VARIANCE_CATEGORY_FULL_FTE_SHORTFALL
    if total_hours < HOURS_PER_FTE:
        return VARIANCE_CATEGORY_PART_FTE_VARIATION
    if total_hours > HOURS_PER_FTE:
        return VARIANCE_CATEGORY_PART_FTE_VARIATION_OVERTIME
    return VARIANCE_CATEGORY_PART_FTE_VARIATION


@dataclass(frozen=True)
class OnlineStudentTarget:
    """UI row for editing online cohort size (qualification or unlinked class)."""

    label: str
    qualification_id: int | None
    unit_id: int | None
    session_count: int


@dataclass(frozen=True)
class StaffHoursSnapshot:
    """Computed timetable slice for one staff member (matches spreadsheet D, G, H)."""

    regular_avg: float
    """Weekly in-class (non-online) hours, averaged across term 1 and term 2."""

    online_avg: float
    """Weekly online load hours (combined cohort rules), averaged across both terms."""

    online_breakdown: str
    """Column G: per class, session counts, student totals, scheduled vs load hours."""

    session_schedule_breakdown: str
    """Per-class semester session averages when fewer than full weeks run."""


def room_is_online(room: Room | None) -> bool:
    """True when the room is online delivery (explicit type or code/name hint)."""
    from .room_types import ROOM_TYPE_ONLINE, room_delivery_type

    if room is None:
        return False
    return room_delivery_type(room) == ROOM_TYPE_ONLINE


def booking_duration_hours(booking: Booking) -> float:
    return (booking.end_slot - booking.start_slot) * (SLOT_MINUTES / 60.0)


def total_scheduled_hours(bookings: Iterable[Booking]) -> float:
    """Sum of raw scheduled slot durations (for week-grid views; no online weighting)."""
    return sum(booking_duration_hours(b) for b in bookings)


def scheduled_hours_by_staff_for_week(
    session: Session, week_id: int, term_filter: str = "all"
) -> dict[int, float]:
    """Per-staff total hours in `week_id`, using the same term filter as the week grid."""
    from .booking_staff import staff_booking_hours_by_term

    acc: defaultdict[int, float] = defaultdict(float)
    for b in session.query(Booking).filter(Booking.week_id == week_id).all():
        hrs = booking_duration_hours(b)
        staff_ids: set[int] = set()
        if b.staff_id is not None:
            staff_ids.add(b.staff_id)
        co = getattr(b, "sfs_co_teacher_staff_id", None)
        if co is not None:
            staff_ids.add(co)
        for sid in staff_ids:
            t1_h, t2_h = staff_booking_hours_by_term(b, sid)
            if term_filter == "t1":
                acc[sid] += t1_h
            elif term_filter == "t2":
                acc[sid] += t2_h
            elif t1_h or t2_h:
                acc[sid] += hrs
    return dict(acc)


def load_unit_qualification_ids(session: Session) -> dict[int, list[int]]:
    out: dict[int, list[int]] = defaultdict(list)
    for unit_id, qualification_id in session.query(
        UnitQualification.unit_id, UnitQualification.qualification_id
    ).all():
        out[unit_id].append(qualification_id)
    return dict(out)


def booking_qualification_ids(
    booking: Booking, unit_qual_ids: dict[int, list[int]]
) -> list[int]:
    """Qualifications that apply to a booking (course link, else all class links)."""
    course = getattr(booking, "course", None)
    if course is not None and course.qualification_id is not None:
        return [int(course.qualification_id)]
    if booking.unit_id is None:
        return []
    return list(unit_qual_ids.get(booking.unit_id, []))


def primary_booking_qualification_id(
    booking: Booking, unit_qual_ids: dict[int, list[int]]
) -> int | None:
    ids = booking_qualification_ids(booking, unit_qual_ids)
    if not ids:
        return None
    if len(ids) == 1:
        return ids[0]
    return min(ids)


def booking_qualification_id(
    booking: Booking, unit_qual_ids: dict[int, list[int]]
) -> int | None:
    return primary_booking_qualification_id(booking, unit_qual_ids)


def load_qualification_online_student_totals(
    session: Session, staff_id: int
) -> dict[int, int | None]:
    return {
        int(row.qualification_id): row.student_count
        for row in session.query(StaffQualificationOnlineStudents).filter_by(staff_id=staff_id).all()
    }


def load_unit_online_student_totals(session: Session, staff_id: int) -> dict[int, int | None]:
    return {
        int(row.unit_id): row.student_count
        for row in session.query(StaffUnitOnlineStudents).filter_by(staff_id=staff_id).all()
    }


def resolve_unit_online_students(
    unit_id: int | None,
    n_sessions: int,
    unit_student_totals: dict[int, int | None],
) -> int:
    if unit_id is not None:
        stored = unit_student_totals.get(unit_id)
        if stored is not None:
            return max(1, int(stored))
    return default_qualification_online_students(n_sessions)


def default_qualification_online_students(n_sessions: int) -> int:
    return max(1, int(n_sessions)) * DEFAULT_ONLINE_STUDENTS


def resolve_qualification_online_students(
    qualification_id: int | None,
    n_sessions: int,
    qual_student_totals: dict[int, int | None],
) -> int:
    if qualification_id is not None:
        stored = qual_student_totals.get(qualification_id)
        if stored is not None:
            return max(1, int(stored))
    return default_qualification_online_students(n_sessions)


def resolve_default_online_students_per_class(staff: Staff | None) -> int:
    """Legacy per-session default when a booking has no qualification or stored total."""
    v = getattr(staff, "default_online_students_per_class", None) if staff is not None else None
    if v is None:
        return DEFAULT_ONLINE_STUDENTS
    return max(1, int(v))


def _effective_online_students(
    booking: Booking,
    *,
    default_per_class: int = DEFAULT_ONLINE_STUDENTS,
) -> int:
    v = getattr(booking, "online_student_count", None)
    if v is None:
        return default_per_class
    return max(1, int(v))


def _group_online_student_total(
    group: list[Booking],
    *,
    unit_qual_ids: dict[int, list[int]],
    qual_student_totals: dict[int, int | None],
    unit_student_totals: dict[int, int | None],
    legacy_default_per_class: int = DEFAULT_ONLINE_STUDENTS,
) -> tuple[int, list[int]]:
    if not group:
        return 0, []
    b0 = group[0]
    # Staff-tab bulk cohort (total students for the class) overrides per-booking
    # headcounts saved from the booking dialog at the default.
    if b0.unit_id is not None:
        stored = unit_student_totals.get(b0.unit_id)
        if stored is not None:
            total = max(1, int(stored))
            return total, [total]
    explicit = [b for b in group if getattr(b, "online_student_count", None) is not None]
    if explicit:
        counts = [
            _effective_online_students(b, default_per_class=legacy_default_per_class)
            for b in group
        ]
        return sum(counts), counts
    # Staff-tab bulk cohort is keyed by class (unit); use unit totals whenever the
    # booking has a class, and fall back to qualification only when there is no unit.
    if b0.unit_id is not None:
        total = resolve_unit_online_students(
            b0.unit_id, len(group), unit_student_totals
        )
    else:
        qual_id = primary_booking_qualification_id(b0, unit_qual_ids)
        if qual_id is not None:
            total = resolve_qualification_online_students(
                qual_id, len(group), qual_student_totals
            )
        else:
            total = default_qualification_online_students(len(group))
    return total, [total]


def lecturing_hours_from_fte(fte: float | None) -> float | None:
    if fte is None:
        return None
    return float(fte) * HOURS_PER_FTE


def _bookings_for_term(bookings: list[Booking], term: int) -> list[Booking]:
    if term == 1:
        return [b for b in bookings if bool(getattr(b, "in_term_1", 1))]
    return [b for b in bookings if bool(getattr(b, "in_term_2", 1))]


def _bookings_for_staff_term(
    bookings: list[Booking], staff_id: int | None, term: int
) -> list[Booking]:
    """Bookings that count toward ``staff_id``'s hours in the given term."""
    if staff_id is None:
        return _bookings_for_term(bookings, term)
    from .booking_staff import staff_active_in_term

    tkey = "t1" if term == 1 else "t2"
    return [b for b in bookings if staff_active_in_term(b, staff_id, tkey)]


def _booking_term_week_factor(booking: Booking, term: int) -> float:
    """Active weeks in one term as a fraction of that term's length (10 weeks)."""
    from .block_delivery import is_block_booking, semester_weeks_for_booking

    if is_block_booking(booking):
        span = TERM1_WEEK_RANGE if term == 1 else TERM2_WEEK_RANGE
        active = [w for w in semester_weeks_for_booking(booking) if w in span]
        return len(active) / 10.0
    active = len(active_session_weeks_in_term(booking, term))
    if term == 1 and not bool(getattr(booking, "in_term_1", 1)):
        return 0.0
    if term == 2 and not bool(getattr(booking, "in_term_2", 1)):
        return 0.0
    return float(active) / 10.0


def _weekly_regular_hours(bookings_term: list[Booking], term: int) -> float:
    """Scheduled contact hours in non-online rooms, session-adjusted for one term."""
    total = 0.0
    for b in bookings_term:
        if room_is_online(b.room):
            continue
        total += booking_duration_hours(b) * _booking_term_week_factor(b, term)
    return total


def _online_group_key(b: Booking) -> int | tuple[str, int]:
    if b.unit_id is not None:
        return b.unit_id
    return ("solo", b.id)


def _weekly_online_hours_and_groups(
    bookings_term: list[Booking],
    term: int,
    *,
    unit_qual_ids: dict[int, list[int]],
    qual_student_totals: dict[int, int | None],
    unit_student_totals: dict[int, int | None],
    legacy_default_per_class: int = DEFAULT_ONLINE_STUDENTS,
) -> tuple[float, list[tuple[str, int, list[int], int, float, float]]]:
    """Returns (total online load hours, group detail rows).

    Each group row: (unit_label, n_sessions, student_counts list, total_students,
                     scheduled_slot_hours, load_hours).
    """
    online_bs = [b for b in bookings_term if room_is_online(b.room)]
    groups: dict[int | tuple[str, int], list[Booking]] = defaultdict(list)
    for b in online_bs:
        groups[_online_group_key(b)].append(b)

    total = 0.0
    details: list[tuple[str, int, list[int], int, float, float]] = []
    for group in groups.values():
        b0 = group[0]
        scheduled_h = sum(booking_duration_hours(b) for b in group)
        total_students, counts = _group_online_student_total(
            group,
            unit_qual_ids=unit_qual_ids,
            qual_student_totals=qual_student_totals,
            unit_student_totals=unit_student_totals,
            legacy_default_per_class=legacy_default_per_class,
        )
        session_h = booking_duration_hours(b0)
        if total_students <= ONLINE_COMBINED_STUDENTS_IN_CLASS_MAX:
            # Up to 34 students: allocate in-class hours (one session), not scaled online load.
            load = session_h
        else:
            load = (
                float(total_students) / float(ONLINE_COMBINED_STUDENTS_FORMULA_DIVISOR)
            ) * 1.5 * session_h
        load *= _booking_term_week_factor(b0, term)
        total += load
        if b0.unit_id and b0.unit is not None:
            label = (b0.unit.name or "").strip() or f"Class #{b0.unit_id}"
        else:
            label = f"(no class) booking #{b0.id}"
        details.append((label, len(group), counts, total_students, scheduled_h, load))
    return total, details


def _weekly_online_hours(
    bookings_term: list[Booking],
    term: int,
    *,
    unit_qual_ids: dict[int, list[int]],
    qual_student_totals: dict[int, int | None],
    unit_student_totals: dict[int, int | None],
    legacy_default_per_class: int = DEFAULT_ONLINE_STUDENTS,
) -> float:
    h, _ = _weekly_online_hours_and_groups(
        bookings_term,
        term,
        unit_qual_ids=unit_qual_ids,
        qual_student_totals=qual_student_totals,
        unit_student_totals=unit_student_totals,
        legacy_default_per_class=legacy_default_per_class,
    )
    return h


def format_online_breakdown(
    bookings: list[Booking],
    *,
    staff_id: int | None = None,
    unit_qual_ids: dict[int, list[int]],
    qual_student_totals: dict[int, int | None],
    unit_student_totals: dict[int, int | None],
    legacy_default_per_class: int = DEFAULT_ONLINE_STUDENTS,
) -> str:
    """Multiline summary for spreadsheet column G."""
    lines: list[str] = []
    for term in (1, 2):
        bt = _bookings_for_staff_term(bookings, staff_id, term)
        _, groups = _weekly_online_hours_and_groups(
            bt,
            term,
            unit_qual_ids=unit_qual_ids,
            qual_student_totals=qual_student_totals,
            unit_student_totals=unit_student_totals,
            legacy_default_per_class=legacy_default_per_class,
        )
        if not groups:
            continue
        lines.append(f"Term {term}:")
        for label, n_sess, counts, tot_stu, slot_h, load in sorted(groups, key=lambda x: x[0].lower()):
            if len(counts) == 1:
                cs = str(counts[0])
            else:
                cs = "+".join(str(c) for c in counts)
            lines.append(
                f"  • {label}: {n_sess} session(s), {tot_stu} students ({cs}), "
                f"{slot_h:.2f}h scheduled → {load:.2f}h load"
            )
    return "\n".join(lines) if lines else "—"


def format_session_schedule_breakdown(
    bookings: list[Booking],
    *,
    staff_id: int | None = None,
) -> str:
    """Multiline summary of semester session averages for partial schedules."""
    from .booking_staff import timetable_staff_ids

    lines: list[str] = []
    for b in sorted(
        bookings,
        key=lambda x: (((x.unit.name or "") if x.unit else ""), x.id),
    ):
        if staff_id is not None and staff_id not in timetable_staff_ids(b):
            continue
        if is_full_session_schedule(b):
            continue
        line = format_session_avg_line(b, booking_duration_hours(b))
        if line:
            lines.append(f"  • {line}")
    return "\n".join(lines) if lines else "—"


def staff_hours_snapshot_for_bookings(
    bookings: list[Booking],
    *,
    staff_id: int | None = None,
    unit_qual_ids: dict[int, list[int]] | None = None,
    qual_student_totals: dict[int, int | None] | None = None,
    unit_student_totals: dict[int, int | None] | None = None,
    legacy_default_per_class: int = DEFAULT_ONLINE_STUDENTS,
) -> StaffHoursSnapshot:
    unit_qual_ids = unit_qual_ids or {}
    qual_student_totals = qual_student_totals or {}
    unit_student_totals = unit_student_totals or {}
    r1 = _weekly_regular_hours(_bookings_for_staff_term(bookings, staff_id, 1), 1)
    r2 = _weekly_regular_hours(_bookings_for_staff_term(bookings, staff_id, 2), 2)
    o1 = _weekly_online_hours(
        _bookings_for_staff_term(bookings, staff_id, 1),
        1,
        unit_qual_ids=unit_qual_ids,
        qual_student_totals=qual_student_totals,
        unit_student_totals=unit_student_totals,
        legacy_default_per_class=legacy_default_per_class,
    )
    o2 = _weekly_online_hours(
        _bookings_for_staff_term(bookings, staff_id, 2),
        2,
        unit_qual_ids=unit_qual_ids,
        qual_student_totals=qual_student_totals,
        unit_student_totals=unit_student_totals,
        legacy_default_per_class=legacy_default_per_class,
    )
    return StaffHoursSnapshot(
        regular_avg=(r1 + r2) / 2.0,
        online_avg=(o1 + o2) / 2.0,
        online_breakdown=format_online_breakdown(
            bookings,
            staff_id=staff_id,
            unit_qual_ids=unit_qual_ids,
            qual_student_totals=qual_student_totals,
            unit_student_totals=unit_student_totals,
            legacy_default_per_class=legacy_default_per_class,
        ),
        session_schedule_breakdown=format_session_schedule_breakdown(
            bookings,
            staff_id=staff_id,
        ),
    )


def staff_hours_snapshots_by_staff_id(session: Session) -> dict[int, StaffHoursSnapshot]:
    unit_qual_ids = load_unit_qualification_ids(session)
    bookings = (
        session.query(Booking)
        .options(
            joinedload(Booking.room),
            joinedload(Booking.unit),
            joinedload(Booking.course),
            joinedload(Booking.staff),
            joinedload(Booking.sfs_co_teacher),
        )
        .all()
    )
    from .booking_staff import timetable_staff_ids

    by_staff: dict[int, list[Booking]] = defaultdict(list)
    for b in bookings:
        for sid in timetable_staff_ids(b):
            by_staff[sid].append(b)
    out: dict[int, StaffHoursSnapshot] = {}
    for s in session.query(Staff).order_by(Staff.id).all():
        qual_student_totals = load_qualification_online_student_totals(session, s.id)
        unit_student_totals = load_unit_online_student_totals(session, s.id)
        legacy_default = resolve_default_online_students_per_class(s)
        out[s.id] = staff_hours_snapshot_for_bookings(
            by_staff.get(s.id, []),
            staff_id=s.id,
            unit_qual_ids=unit_qual_ids,
            qual_student_totals=qual_student_totals,
            unit_student_totals=unit_student_totals,
            legacy_default_per_class=legacy_default,
        )
    return out


def online_student_targets_for_staff(
    session: Session, staff_id: int
) -> list[OnlineStudentTarget]:
    """One row per class (unit) the lecturer teaches online; duplicate lots merged."""
    bookings = (
        session.query(Booking)
        .options(joinedload(Booking.course), joinedload(Booking.room), joinedload(Booking.unit))
        .filter(Booking.staff_id == staff_id)
        .all()
    )
    unit_counts: dict[int, int] = defaultdict(int)
    for b in bookings:
        if not room_is_online(b.room):
            continue
        if b.unit_id is None:
            continue
        unit_counts[b.unit_id] += 1
    if not unit_counts:
        return []
    unit_names = {
        u.id: u.name
        for u in session.query(Unit).filter(Unit.id.in_(unit_counts)).all()
    }
    targets: list[OnlineStudentTarget] = []
    for unit_id in sorted(unit_counts, key=lambda uid: (unit_names.get(uid) or "").lower()):
        label = (unit_names.get(unit_id) or "").strip() or f"Class #{unit_id}"
        targets.append(
            OnlineStudentTarget(
                label=label,
                qualification_id=None,
                unit_id=unit_id,
                session_count=unit_counts[unit_id],
            )
        )
    return targets


def online_qualifications_for_staff(
    session: Session, staff_id: int
) -> list[tuple[int, str, int]]:
    """Legacy hook: bulk online cohorts are keyed by class (unit), not qualification."""
    return []


def timetabled_hours_averaged_terms(bookings: list[Booking]) -> float:
    """Weekly contact hours (regular + online), averaged across term 1 and term 2."""
    snap = staff_hours_snapshot_for_bookings(bookings)
    return snap.regular_avg + snap.online_avg


def timetabled_hours_by_staff_id(session: Session) -> dict[int, float]:
    """Combined weekly timetabled hours (regular + online), averaged across terms."""
    snaps = staff_hours_snapshots_by_staff_id(session)
    return {sid: snap.regular_avg + snap.online_avg for sid, snap in snaps.items()}


def spreadsheet_total_hours(
    regular_avg: float,
    online_avg: float,
    ot: float | None,
    development: float | None,
    tae: float | None,
    supervision: float | None,
) -> float:
    """Column L: timetable contact + OT + dev + TAE + supervision."""
    return (
        float(regular_avg)
        + float(online_avg)
        + (float(ot) if ot is not None else 0.0)
        + (float(development) if development is not None else 0.0)
        + (float(tae) if tae is not None else 0.0)
        + (float(supervision) if supervision is not None else 0.0)
    )


def staff_tab_total_hours(staff: Staff, snap: StaffHoursSnapshot) -> float:
    """Same value as the Staff editor **Total** column (not raw week-grid slot hours).

    Combines averaged timetabled contact (regular + online load rules) with
    development & project, PD run training, and supervision from ``Staff``.
    """
    return spreadsheet_total_hours(
        snap.regular_avg,
        snap.online_avg,
        None,
        getattr(staff, "development_project_hours", None),
        getattr(staff, "tae_hours", None),
        getattr(staff, "supervision_hours", None),
    )


def staff_tab_total_hours_by_staff_id(session: Session) -> dict[int, float]:
    """``Staff.id`` → Staff-tab Total, for sidebars and headings."""
    try:
        snap_map = staff_hours_snapshots_by_staff_id(session)
    except Exception:
        return {}
    out: dict[int, float] = {}
    for s in session.query(Staff).order_by(Staff.id).all():
        out[s.id] = staff_tab_total_hours(s, snap_map.get(s.id) or staff_hours_snapshot_for_bookings([]))
    return out


def safe_staff_tab_total_hours_by_staff_id(session: Session) -> dict[int, float]:
    """Like :func:`staff_tab_total_hours_by_staff_id` but never raises (sidebar safety)."""
    try:
        return staff_tab_total_hours_by_staff_id(session)
    except Exception:
        return {}


def _class_display_name(bookings: list[Booking], unit_id: int | None) -> str:
    for b in bookings:
        if b.unit_id == unit_id and b.unit is not None:
            return (b.unit.name or "").strip() or f"Class #{unit_id}"
    if unit_id is None:
        return "(no class)"
    return f"Class #{unit_id}"


def _term_class_hours_by_unit(
    bookings: list[Booking],
    staff_id: int,
    term: int,
    *,
    unit_qual_ids: dict[int, list[int]],
    qual_student_totals: dict[int, int | None],
    unit_student_totals: dict[int, int | None],
    legacy_default_per_class: int,
) -> dict[int | None, float]:
    """Per-class hours in one term (scheduled face-to-face + online load rules)."""
    from .booking_staff import staff_active_in_term

    tkey = "t1" if term == 1 else "t2"
    bt = [b for b in bookings if staff_active_in_term(b, staff_id, tkey)]
    by_unit: dict[int | None, list[Booking]] = defaultdict(list)
    for b in bt:
        by_unit[b.unit_id].append(b)
    out: dict[int | None, float] = {}
    for unit_id, group in by_unit.items():
        regular = sum(
            booking_duration_hours(b) * _booking_term_week_factor(b, term)
            for b in group
            if not room_is_online(b.room)
        )
        online = _weekly_online_hours(
            group,
            term,
            unit_qual_ids=unit_qual_ids,
            qual_student_totals=qual_student_totals,
            unit_student_totals=unit_student_totals,
            legacy_default_per_class=legacy_default_per_class,
        )
        out[unit_id] = regular + online
    return out


def class_hours_summary_for_staff_export(
    session: Session,
    staff_id: int,
    bookings: list[Booking],
) -> tuple[list[tuple[str, float]], float]:
    """Per-class weekly hours (term-averaged) for Export v2 staff summary columns.

    Online/Collaborate rooms use the same load rules as the Staff tab, not raw slot hours.
    """
    if not bookings:
        return [], 0.0
    unit_qual_ids = load_unit_qualification_ids(session)
    qual_totals = load_qualification_online_student_totals(session, staff_id)
    unit_totals = load_unit_online_student_totals(session, staff_id)
    staff = session.get(Staff, staff_id)
    legacy = resolve_default_online_students_per_class(staff)
    ctx = dict(
        unit_qual_ids=unit_qual_ids,
        qual_student_totals=qual_totals,
        unit_student_totals=unit_totals,
        legacy_default_per_class=legacy,
    )
    t1 = _term_class_hours_by_unit(bookings, staff_id, 1, **ctx)
    t2 = _term_class_hours_by_unit(bookings, staff_id, 2, **ctx)
    rows: list[tuple[str, float]] = []
    for unit_id in sorted(
        set(t1) | set(t2),
        key=lambda uid: _class_display_name(bookings, uid).lower(),
    ):
        hours = (t1.get(unit_id, 0.0) + t2.get(unit_id, 0.0)) / 2.0
        if hours <= 0:
            continue
        rows.append((_class_display_name(bookings, unit_id), hours))
    return rows, sum(h for _, h in rows)


# Labels for Export v2 staff sheet hours summary (columns AA–AB).
STAFF_V2_SUMMARY_EXTRA_ROW_LABELS = (
    "Development & project",
    "PD run training",
    "Supervision",
)


def staff_v2_hours_summary_footer(
    session: Session,
    staff_id: int,
    bookings: list[Booking],
) -> tuple[list[tuple[str, float | None]], float, float | None]:
    """Non-timetabled hour rows, grand total, and FTE variance for Export v2 staff summary."""
    staff = session.get(Staff, staff_id)
    if staff is None:
        return [], 0.0, None
    unit_qual_ids = load_unit_qualification_ids(session)
    qual_totals = load_qualification_online_student_totals(session, staff_id)
    unit_totals = load_unit_online_student_totals(session, staff_id)
    snap = staff_hours_snapshot_for_bookings(
        bookings,
        staff_id=staff_id,
        unit_qual_ids=unit_qual_ids,
        qual_student_totals=qual_totals,
        unit_student_totals=unit_totals,
        legacy_default_per_class=resolve_default_online_students_per_class(staff),
    )
    extra_rows = [
        (label, getattr(staff, field, None))
        for label, field in (
            (STAFF_V2_SUMMARY_EXTRA_ROW_LABELS[0], "development_project_hours"),
            (STAFF_V2_SUMMARY_EXTRA_ROW_LABELS[1], "tae_hours"),
            (STAFF_V2_SUMMARY_EXTRA_ROW_LABELS[2], "supervision_hours"),
        )
    ]
    grand_total = staff_tab_total_hours(staff, snap)
    lh = lecturing_hours_from_fte(staff.fte)
    variance = (grand_total - lh) if lh is not None else None
    return extra_rows, grand_total, variance

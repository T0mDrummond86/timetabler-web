"""Build timetable grid payloads for all desktop view kinds."""
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from timetable.constants import DAYS, FIRST_SLOT_TIME, NUM_DAYS, NUM_SLOTS, SLOT_MINUTES
from timetable.core.booking_sessions import booking_runs_in_semester_week
from timetable.core.booking_staff import (
    sfs_co_teacher_booking_filter,
    sfs_co_teacher_term_labels,
    staff_booking_filter_sql,
)
from timetable.core.staff_hours import room_is_online
from timetable.core.class_colour import booking_colour_key
from timetable.core.class_colour_overrides import build_screen_colour_map
from timetable.core.models import Booking, Course, Room, Semester, Staff, StaffAvailability, Unit, Week
from timetable.core.schedule_variants import apply_schedule_display_filter, variant_week_buttons
from timetable.core.tenancy_models import TimetableSession
from timetable.core.unassigned_lecturer import bookings_without_lecturer
from timetable.core.validation import Severity, _iter_violations

from ..colours import class_colours
from .violation_dismissals import apply_dismissals_to_map, dismissed_keys

ColumnKind = Literal["day", "room", "staff"]

VALID_VIEWS = frozenset(
    {
        "course",
        "course_semester",
        "staff",
        "room",
        "day",
        "unassigned_lecturer",
        "co_teach",
        "block_delivery",
    }
)


def _violations_by_booking_id(violations) -> dict[int, list]:
    out: dict[int, list] = defaultdict(list)
    for v in violations:
        for bid in v.booking_ids:
            out[bid].append(v)
    return out


def _assign_lanes(bookings: list[Booking]) -> tuple[dict[int, int], int]:
    from timetable.core.validation import bookings_need_separate_lanes

    sorted_b = sorted(bookings, key=lambda b: (b.start_slot, b.end_slot))
    lane_index: dict[int, int] = {}
    lanes: list[list[Booking]] = []
    for b in sorted_b:
        placed = False
        for i, occupants in enumerate(lanes):
            if any(bookings_need_separate_lanes(b, x) for x in occupants):
                continue
            occupants.append(b)
            lane_index[b.id] = i
            placed = True
            break
        if not placed:
            lanes.append([b])
            lane_index[b.id] = len(lanes) - 1
    return lane_index, max(1, len(lanes))


def _lane_depth_for_booking(booking: Booking, all_col: list[Booking]) -> int:
    depth = 1
    for t in range(booking.start_slot, booking.end_slot):
        active = [b for b in all_col if b.start_slot <= t < b.end_slot]
        _, n_at = _assign_lanes(active)
        depth = max(depth, n_at)
    return depth


def get_repeating_week(db: Session, timetable_session_id: int) -> Week | None:
    sem = (
        db.query(Semester)
        .filter(Semester.timetable_session_id == timetable_session_id)
        .first()
    )
    if sem is None:
        return None
    return (
        db.query(Week)
        .filter(Week.semester_id == sem.id, Week.week_number == 0)
        .first()
    )


def assert_session_in_org(db: Session, session_id: int, org_id: int) -> TimetableSession:
    row = (
        db.query(TimetableSession)
        .filter(
            TimetableSession.id == session_id,
            TimetableSession.organization_id == org_id,
        )
        .first()
    )
    if row is None:
        raise LookupError("Session not found")
    return row


def list_courses(db: Session, timetable_session_id: int) -> list[Course]:
    return (
        db.query(Course)
        .filter(Course.timetable_session_id == timetable_session_id)
        .order_by(Course.code)
        .all()
    )


def count_bookings_on_day(db: Session, timetable_session_id: int, day: int) -> int:
    week = get_repeating_week(db, timetable_session_id)
    if week is None or not (0 <= day < NUM_DAYS):
        return 0
    return (
        db.query(Booking)
        .filter(
            Booking.week_id == week.id,
            Booking.day == day,
            Booking.block_week_index.is_(None),
        )
        .count()
    )


def scheduled_hours_on_day(db: Session, timetable_session_id: int, day: int) -> float:
    week = get_repeating_week(db, timetable_session_id)
    if week is None or not (0 <= day < NUM_DAYS):
        return 0.0
    total_slots = (
        db.query(func.coalesce(func.sum(Booking.end_slot - Booking.start_slot), 0))
        .filter(
            Booking.week_id == week.id,
            Booking.day == day,
            Booking.block_week_index.is_(None),
        )
        .scalar()
    )
    return int(total_slots) * SLOT_MINUTES / 60.0


def _booking_query(db: Session, week_id: int):
    return (
        db.query(Booking)
        .options(
            joinedload(Booking.unit),
            joinedload(Booking.course),
            joinedload(Booking.staff),
            joinedload(Booking.sfs_co_teacher),
            joinedload(Booking.room),
        )
        .filter(Booking.week_id == week_id)
    )


def _co_teacher_staff_line(b: Booking) -> str | None:
    co = getattr(b, "sfs_co_teacher", None)
    if co is None:
        return None
    primary = b.staff.name if b.staff else ""
    co_name = co.name
    terms = sfs_co_teacher_term_labels(b)
    co_part = co_name + (f" ({terms})" if terms else "")
    if primary:
        return f"{primary} + {co_part}"
    return co_part


def _booking_card(
    b: Booking,
    *,
    view: str,
    column: int,
    lane: int,
    lane_depth: int,
    v_by_booking: dict,
    hard_ids: set[int],
    soft_ids: set[int],
    colour_by_class: bool = True,
    screen_colour_map: dict[str, tuple[str, str]] | None = None,
) -> dict:
    colour_key = booking_colour_key(b, by_class=colour_by_class)
    fill, border = class_colours(colour_key, screen_colour_map)
    b_violations = v_by_booking.get(b.id, [])
    staff_name = b.staff.name if b.staff else None
    if view == "co_teach":
        staff_name = _co_teacher_staff_line(b)
    return {
        "id": b.id,
        "course_id": b.course_id,
        "day": b.day,
        "column": column,
        "start_slot": b.start_slot,
        "end_slot": b.end_slot,
        "lane": lane,
        "lane_depth": lane_depth,
        "unit_name": b.unit.name if b.unit else None,
        "course_code": b.course.code if b.course else None,
        "staff_name": staff_name,
        "room_code": b.room.code if b.room else None,
        "room_id": b.room_id,
        "notes": b.notes,
        "external_id": b.external_id,
        "colour_key": colour_key,
        "fill_colour": fill,
        "border_colour": border,
        "is_hard": b.id in hard_ids,
        "is_soft": b.id in soft_ids and b.id not in hard_ids,
        "lock_time": bool(getattr(b, "lock_time", 0)),
        "lock_staff": bool(getattr(b, "lock_staff", 0)),
        "in_term_1": bool(getattr(b, "in_term_1", 0)),
        "in_term_2": bool(getattr(b, "in_term_2", 0)),
        "unit_id": b.unit_id,
        "unit_screen_fill_colour": (
            b.unit.screen_fill_colour if b.unit and b.unit.screen_fill_colour else None
        ),
        "session_part": getattr(b, "session_part", 1) or 1,
        "sfs_co_teacher_staff_id": getattr(b, "sfs_co_teacher_staff_id", None),
        "sfs_co_teacher_name": (
            b.sfs_co_teacher.name if getattr(b, "sfs_co_teacher", None) else None
        ),
        "sfs_co_teacher_in_term_1": bool(getattr(b, "sfs_co_teacher_in_term_1", 0)),
        "sfs_co_teacher_in_term_2": bool(getattr(b, "sfs_co_teacher_in_term_2", 0)),
        "online_student_count": getattr(b, "online_student_count", None),
        "room_is_online": room_is_online(b.room),
        "violations": [
            {
                "severity": v.severity.value,
                "code": v.code,
                "message": v.message,
            }
            for v in b_violations
        ],
    }


def _build_grid_payload(
    db: Session,
    *,
    timetable_session_id: int,
    week: Week,
    bookings: list[Booking],
    view: str,
    entity_id: int,
    entity_label: str,
    columns: list[str],
    column_kind: ColumnKind,
    column_ids: list[int | None] | None = None,
    focus_day: int | None = None,
    course_id: int | None = None,
    course_code: str | None = None,
    semester_week: int | None = None,
    block_week_index: int | None = None,
    readonly: bool = False,
    schedule_variants: list[dict] | None = None,
    preview_semester_week: int | None = None,
    unavailable_slots: dict[str, list[int]] | None = None,
    linked_session_busy_slots: dict[str, list[int]] | None = None,
    linked_session_busy_label: str | None = None,
    staff_hours: float | None = None,
    colour_by_class: bool = True,
    hide_dismissed: bool = True,
) -> dict:
    violations = list(_iter_violations(db, bookings))
    dismissed = dismissed_keys(db, timetable_session_id=timetable_session_id) if hide_dismissed else set()
    v_by_booking_raw = _violations_by_booking_id(violations)
    v_by_booking = apply_dismissals_to_map(dismissed, v_by_booking_raw) if dismissed else v_by_booking_raw
    hard_ids = {
        bid
        for v in violations
        if v.severity == Severity.HARD
        for bid in v.booking_ids
        if not dismissed or (bid, v.code) not in dismissed
    }
    soft_ids = {
        bid
        for v in violations
        if v.severity == Severity.SOFT
        for bid in v.booking_ids
        if bid not in hard_ids and (not dismissed or (bid, v.code) not in dismissed)
    }

    by_column: dict[int, list[Booking]] = defaultdict(list)
    if column_kind == "day":
        for b in bookings:
            by_column[b.day].append(b)
    elif column_kind == "staff":
        staff_to_col = {
            sid: idx for idx, sid in enumerate(column_ids or []) if sid is not None
        }
        unassigned_col = len(column_ids or []) - 1 if column_ids and column_ids[-1] is None else None
        for b in bookings:
            if b.staff_id is None and unassigned_col is not None:
                by_column[unassigned_col].append(b)
            elif b.staff_id is not None and b.staff_id in staff_to_col:
                by_column[staff_to_col[b.staff_id]].append(b)
    else:
        room_to_col = {
            rid: idx for idx, rid in enumerate(column_ids or []) if rid is not None
        }
        for b in bookings:
            if b.room_id is not None and b.room_id in room_to_col:
                by_column[room_to_col[b.room_id]].append(b)

    units = (
        db.query(Unit)
        .filter(Unit.timetable_session_id == timetable_session_id)
        .all()
    )
    screen_colour_map = build_screen_colour_map(
        bookings,
        colour_by_class=colour_by_class,
        units=units,
    )

    cards: list[dict] = []
    for col_idx in range(len(columns)):
        col_bookings = by_column.get(col_idx, [])
        if not col_bookings:
            continue
        lane_index, _ = _assign_lanes(col_bookings)
        for b in col_bookings:
            cards.append(
                _booking_card(
                    b,
                    view=view,
                    column=col_idx,
                    lane=lane_index.get(b.id, 0),
                    lane_depth=_lane_depth_for_booking(b, col_bookings),
                    v_by_booking=v_by_booking,
                    hard_ids=hard_ids,
                    soft_ids=soft_ids,
                    colour_by_class=colour_by_class,
                    screen_colour_map=screen_colour_map,
                )
            )

    card_ids = {c["id"] for c in cards}
    relevant = [v for v in violations if any(bid in card_ids for bid in v.booking_ids)]

    return {
        "timetable_session_id": timetable_session_id,
        "view": view,
        "entity_id": entity_id,
        "entity_label": entity_label,
        "course_id": course_id,
        "course_code": course_code,
        "week_id": week.id,
        "week_label": week.label or "Repeating week",
        "column_kind": column_kind,
        "focus_day": focus_day,
        "columns": columns,
        "days": list(DAYS),
        "num_slots": NUM_SLOTS,
        "slot_minutes": SLOT_MINUTES,
        "first_slot_time": FIRST_SLOT_TIME.strftime("%H:%M"),
        "bookings": cards,
        "violations": [
            {
                "severity": v.severity.value,
                "code": v.code,
                "message": v.message,
                "booking_ids": list(v.booking_ids),
            }
            for v in relevant[:20]
        ],
        "semester_week": semester_week,
        "block_week_index": block_week_index,
        "readonly": readonly,
        "schedule_variants": schedule_variants or [],
        "preview_semester_week": preview_semester_week,
        "unavailable_slots": unavailable_slots,
        "linked_session_busy_slots": linked_session_busy_slots,
        "linked_session_busy_label": linked_session_busy_label,
        "staff_hours": staff_hours,
    }


def _fetch_bookings(
    db: Session,
    week_id: int,
    view: str,
    *,
    course_id: int | None = None,
    staff_id: int | None = None,
    day: int | None = None,
    block_week_index: int | None = None,
    semester_week: int | None = None,
) -> list[Booking]:
    q = _booking_query(db, week_id)
    if block_week_index is not None:
        q = q.filter(Booking.block_week_index == block_week_index)
    elif view != "block_delivery":
        q = q.filter(Booking.block_week_index.is_(None))

    if view in ("course", "course_semester", "co_teach", "block_delivery"):
        q = q.filter(Booking.course_id == course_id)
    elif view == "staff":
        q = q.filter(staff_booking_filter_sql(staff_id, "all"))
    elif view == "room":
        q = q.filter(Booking.day == day)
    elif view == "day":
        q = q.filter(Booking.day == day)
    elif view == "unassigned_lecturer":
        q = q.filter(Booking.staff_id.is_(None))

    if view == "co_teach":
        q = q.filter(sfs_co_teacher_booking_filter())

    bookings = q.all()

    if view in ("course", "course_semester") and block_week_index is None:
        if view == "course_semester":
            bookings = apply_schedule_display_filter(
                bookings, semester_week=semester_week, standard_only=False
            )
        elif semester_week is not None:
            bookings = apply_schedule_display_filter(
                bookings, semester_week=semester_week, standard_only=False
            )
        else:
            bookings = apply_schedule_display_filter(bookings, standard_only=True)
    elif semester_week is not None and view not in ("course", "course_semester"):
        bookings = [b for b in bookings if booking_runs_in_semester_week(b, semester_week)]

    return bookings


def _staff_unavailable_slots(db: Session, staff_id: int) -> dict[str, list[int]] | None:
    windows = (
        db.query(StaffAvailability)
        .filter(StaffAvailability.staff_id == staff_id)
        .all()
    )
    if not windows:
        return None
    available_by_day: dict[int, set[int]] = {d: set() for d in range(NUM_DAYS)}
    for w in windows:
        if 0 <= w.day < NUM_DAYS:
            for s in range(max(0, w.start_slot), min(NUM_SLOTS, w.end_slot)):
                available_by_day[w.day].add(s)
    out: dict[str, list[int]] = {}
    for d in range(NUM_DAYS):
        unavailable = sorted(s for s in range(NUM_SLOTS) if s not in available_by_day[d])
        if unavailable:
            out[str(d)] = unavailable
    return out or None


def _course_schedule_variants(db: Session, week_id: int, course_id: int) -> list[dict]:
    raw = (
        _booking_query(db, week_id)
        .filter(Booking.course_id == course_id, Booking.block_week_index.is_(None))
        .all()
    )
    return [{"label": label, "preview_week": week} for label, week in variant_week_buttons(raw)]


def build_course_timetable(
    db: Session,
    *,
    timetable_session_id: int,
    course_id: int,
    semester_week: int | None = None,
    view: str = "course",
    colour_by_class: bool = True,
    hide_dismissed: bool = True,
) -> dict:
    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.timetable_session_id == timetable_session_id)
        .first()
    )
    if course is None:
        raise LookupError("Course not found")
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    bookings = _fetch_bookings(
        db,
        week.id,
        view,
        course_id=course_id,
        semester_week=semester_week if view != "course" or semester_week else None,
    )
    variants = _course_schedule_variants(db, week.id, course_id) if view == "course" else []
    preview = semester_week if view == "course" and semester_week else None
    return _build_grid_payload(
        db,
        timetable_session_id=timetable_session_id,
        week=week,
        bookings=bookings,
        view=view,
        entity_id=course.id,
        entity_label=course.code,
        columns=list(DAYS),
        column_kind="day",
        course_id=course.id,
        course_code=course.code,
        semester_week=semester_week if view == "course_semester" else None,
        schedule_variants=variants,
        preview_semester_week=preview,
        colour_by_class=colour_by_class,
        hide_dismissed=hide_dismissed,
    )


def build_staff_timetable(
    db: Session,
    *,
    timetable_session_id: int,
    staff_id: int,
    colour_by_class: bool = True,
    hide_dismissed: bool = True,
) -> dict:
    staff = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.timetable_session_id == timetable_session_id)
        .first()
    )
    if staff is None:
        raise LookupError("Staff not found")
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    bookings = _fetch_bookings(db, week.id, "staff", staff_id=staff_id)
    from .global_staff_hours import staff_tab_total_hours_for_staff

    hours = staff_tab_total_hours_for_staff(db, staff)
    from .global_sessions import linked_session_busy_slots

    linked_busy, linked_label = linked_session_busy_slots(
        db,
        timetable_session_id=timetable_session_id,
        staff_id=staff.id,
    )
    return _build_grid_payload(
        db,
        timetable_session_id=timetable_session_id,
        week=week,
        bookings=bookings,
        view="staff",
        entity_id=staff.id,
        entity_label=staff.name,
        columns=list(DAYS),
        column_kind="day",
        unavailable_slots=_staff_unavailable_slots(db, staff.id),
        linked_session_busy_slots=linked_busy,
        linked_session_busy_label=linked_label,
        staff_hours=hours,
        colour_by_class=colour_by_class,
        hide_dismissed=hide_dismissed,
    )


def build_room_timetable(
    db: Session,
    *,
    timetable_session_id: int,
    day: int,
    colour_by_class: bool = True,
    hide_dismissed: bool = True,
) -> dict:
    if day < 0 or day >= NUM_DAYS:
        raise ValueError(f"day must be 0–{NUM_DAYS - 1}")
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    rooms = (
        db.query(Room)
        .filter(Room.timetable_session_id == timetable_session_id)
        .order_by(Room.code)
        .all()
    )
    bookings = _fetch_bookings(db, week.id, "room", day=day)
    columns = [r.code for r in rooms]
    column_ids = [r.id for r in rooms]
    return _build_grid_payload(
        db,
        timetable_session_id=timetable_session_id,
        week=week,
        bookings=bookings,
        view="room",
        entity_id=day,
        entity_label=DAYS[day],
        columns=columns,
        column_kind="room",
        column_ids=column_ids,
        focus_day=day,
        colour_by_class=colour_by_class,
        hide_dismissed=hide_dismissed,
    )


def build_day_timetable(
    db: Session,
    *,
    timetable_session_id: int,
    day: int,
    colour_by_class: bool = True,
    hide_dismissed: bool = True,
) -> dict:
    if day < 0 or day >= NUM_DAYS:
        raise ValueError(f"day must be 0–{NUM_DAYS - 1}")
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    bookings = _fetch_bookings(db, week.id, "day", day=day)
    staff_list = (
        db.query(Staff)
        .filter(Staff.timetable_session_id == timetable_session_id)
        .order_by(Staff.name)
        .all()
    )
    has_unassigned = any(b.staff_id is None for b in bookings)
    columns: list[str] = [s.name for s in staff_list]
    column_ids: list[int | None] = [s.id for s in staff_list]
    if has_unassigned:
        columns.append("Unassigned")
        column_ids.append(None)
    return _build_grid_payload(
        db,
        timetable_session_id=timetable_session_id,
        week=week,
        bookings=bookings,
        view="day",
        entity_id=day,
        entity_label=DAYS[day],
        columns=columns,
        column_kind="staff",
        column_ids=column_ids,
        focus_day=day,
        readonly=True,
        colour_by_class=colour_by_class,
        hide_dismissed=hide_dismissed,
    )


def build_unassigned_timetable(
    db: Session,
    *,
    timetable_session_id: int,
    colour_by_class: bool = True,
    hide_dismissed: bool = True,
) -> dict:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    bookings = bookings_without_lecturer(db, week.id)
    return _build_grid_payload(
        db,
        timetable_session_id=timetable_session_id,
        week=week,
        bookings=bookings,
        view="unassigned_lecturer",
        entity_id=0,
        entity_label="Unassigned lecturer",
        columns=list(DAYS),
        column_kind="day",
        colour_by_class=colour_by_class,
        hide_dismissed=hide_dismissed,
    )


def build_co_teach_timetable(
    db: Session,
    *,
    timetable_session_id: int,
    course_id: int,
    colour_by_class: bool = True,
    hide_dismissed: bool = True,
) -> dict:
    return build_course_timetable(
        db,
        timetable_session_id=timetable_session_id,
        course_id=course_id,
        view="co_teach",
        colour_by_class=colour_by_class,
        hide_dismissed=hide_dismissed,
    )


def build_block_delivery_timetable(
    db: Session,
    *,
    timetable_session_id: int,
    course_id: int,
    block_week_index: int,
    colour_by_class: bool = True,
    hide_dismissed: bool = True,
) -> dict:
    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.timetable_session_id == timetable_session_id)
        .first()
    )
    if course is None:
        raise LookupError("Course not found")
    if block_week_index < 1:
        raise ValueError("block_week_index must be >= 1")
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")
    bookings = _fetch_bookings(
        db,
        week.id,
        "block_delivery",
        course_id=course_id,
        block_week_index=block_week_index,
    )
    return _build_grid_payload(
        db,
        timetable_session_id=timetable_session_id,
        week=week,
        bookings=bookings,
        view="block_delivery",
        entity_id=course.id,
        entity_label=course.code,
        columns=list(DAYS),
        column_kind="day",
        course_id=course.id,
        course_code=course.code,
        block_week_index=block_week_index,
        colour_by_class=colour_by_class,
        hide_dismissed=hide_dismissed,
    )


def build_timetable(
    db: Session,
    *,
    timetable_session_id: int,
    view: str,
    course_id: int | None = None,
    staff_id: int | None = None,
    day: int | None = None,
    semester_week: int | None = None,
    block_week_index: int | None = None,
    colour_by_class: bool = True,
    hide_dismissed: bool = True,
) -> dict:
    if view not in VALID_VIEWS:
        raise ValueError(f"Unknown view: {view}")

    if view in ("course", "course_semester", "co_teach"):
        if course_id is None:
            raise ValueError("course_id is required")
        sw = semester_week if view == "course_semester" else semester_week
        if view == "course_semester" and sw is None:
            sw = 1
        if view == "co_teach":
            return build_co_teach_timetable(
                db,
                timetable_session_id=timetable_session_id,
                course_id=course_id,
                colour_by_class=colour_by_class,
                hide_dismissed=hide_dismissed,
            )
        return build_course_timetable(
            db,
            timetable_session_id=timetable_session_id,
            course_id=course_id,
            semester_week=sw,
            view=view,
            colour_by_class=colour_by_class,
            hide_dismissed=hide_dismissed,
        )
    if view == "staff":
        if staff_id is None:
            raise ValueError("staff_id is required")
        return build_staff_timetable(
            db,
            timetable_session_id=timetable_session_id,
            staff_id=staff_id,
            colour_by_class=colour_by_class,
            hide_dismissed=hide_dismissed,
        )
    if view == "room":
        d = 0 if day is None else day
        return build_room_timetable(
            db,
            timetable_session_id=timetable_session_id,
            day=d,
            colour_by_class=colour_by_class,
            hide_dismissed=hide_dismissed,
        )
    if view == "day":
        if day is None:
            raise ValueError("day is required")
        return build_day_timetable(
            db,
            timetable_session_id=timetable_session_id,
            day=day,
            colour_by_class=colour_by_class,
            hide_dismissed=hide_dismissed,
        )
    if view == "unassigned_lecturer":
        return build_unassigned_timetable(
            db,
            timetable_session_id=timetable_session_id,
            colour_by_class=colour_by_class,
            hide_dismissed=hide_dismissed,
        )
    if view == "block_delivery":
        if course_id is None:
            raise ValueError("course_id is required for block delivery")
        if block_week_index is None:
            raise ValueError("block_week_index is required for block delivery")
        return build_block_delivery_timetable(
            db,
            timetable_session_id=timetable_session_id,
            course_id=course_id,
            block_week_index=block_week_index,
            colour_by_class=colour_by_class,
            hide_dismissed=hide_dismissed,
        )
    raise ValueError(f"Unhandled view: {view}")

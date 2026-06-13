"""Timetable print layout — same rules as the desktop print preview (no Qt)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session, joinedload

from ..constants import DAYS, NUM_DAYS, NUM_SLOTS
from ..core.booking_staff import export_lecturer_label, staff_booking_filter_sql
from ..core.models import Booking, Room, StaffAvailability, Unit
from ..core.print_colours import (
    build_print_fill_by_booking_id,
    collect_print_tint_keys,
    assign_print_colours,
    violation_kind_for_booking,
)
from ..core.staff_hours import room_is_online
from ..core.validation import Severity, validate_bookings
from .xlsm_export import (
    _bookings_by_slot,
    _class_title_line,
    _component_codes_line,
    _split_pairs,
    _terms_of,
    placecard_subject_block,
)

PrintKind = Literal["course", "staff", "room"]
PrintJobKind = Literal["course", "staff", "room", "course_staff", "changed_courses"]
PrintLane = Literal["full", "left", "right"]
PrintTerm = Literal["t1", "t2"]
TermLayout = Literal["full", "t1_only", "t2_only", "term_pair", "merged_online"]


@dataclass(frozen=True)
class PrintPaintUnit:
    bookings: tuple[Booking, ...]
    term_layout: TermLayout


@dataclass(frozen=True)
class PrintCardDraw:
    """One card region on the grid."""

    day: int
    start_slot: int
    end_slot: int
    sub_lane: int
    sub_lane_count: int
    lane: PrintLane
    lines: tuple[str, ...]
    fill_hex: str
    booking_id: int
    violation: str | None = None


@dataclass(frozen=True)
class TimetablePrintPage:
    headline: str
    kind: PrintKind
    cards: tuple[PrintCardDraw, ...]
    unavailable_by_day: dict[int, set[int]] | None


@dataclass(frozen=True)
class PrintEntitySpec:
    """One printable timetable (course, staff, or room row)."""

    kind: PrintKind
    entity_id: int
    label: str


def headline_for(kind: PrintKind, name: str) -> str:
    if kind == "course":
        return f"Course timetable — {name}"
    if kind == "staff":
        return f"Staff timetable — {name}"
    return f"Room timetable — {name}"


def load_entity_bookings(
    session: Session,
    *,
    week_id: int,
    kind: PrintKind,
    entity_id: int,
    term_filter: str,
    violations_cache: list | None = None,
) -> tuple[list[Booking], set[int], set[int], dict[int, set[int]] | None]:
    q = (
        session.query(Booking)
        .options(
            joinedload(Booking.unit),
            joinedload(Booking.course),
            joinedload(Booking.staff),
            joinedload(Booking.sfs_co_teacher),
            joinedload(Booking.room),
        )
        .filter(Booking.week_id == week_id)
    )
    if kind == "course":
        q = q.filter(Booking.course_id == entity_id)
    elif kind == "staff":
        q = q.filter(staff_booking_filter_sql(entity_id, term_filter))
    elif kind == "room":
        q = q.filter(Booking.room_id == entity_id)
    if kind != "staff":
        if term_filter == "t1":
            q = q.filter(Booking.in_term_1 == 1)
        elif term_filter == "t2":
            q = q.filter(Booking.in_term_2 == 1)
    bookings = [b for b in q.all() if 0 <= b.day < NUM_DAYS]
    missing_unit_ids = {b.unit_id for b in bookings if b.unit is None and b.unit_id}
    if missing_unit_ids:
        units = {u.id: u for u in session.query(Unit).filter(Unit.id.in_(missing_unit_ids)).all()}
        for b in bookings:
            if b.unit is None and b.unit_id in units:
                b.unit = units[b.unit_id]

    violations = (
        violations_cache if violations_cache is not None else validate_bookings(session, week_id)
    )
    hard_ids = {bid for v in violations if v.severity == Severity.HARD for bid in v.booking_ids}
    soft_ids = {bid for v in violations if v.severity == Severity.SOFT for bid in v.booking_ids}

    unavailable_by_day: dict[int, set[int]] | None = None
    if kind == "staff":
        windows = (
            session.query(StaffAvailability)
            .filter(StaffAvailability.staff_id == entity_id)
            .all()
        )
        if windows:
            available_by_day: dict[int, set[int]] = {d: set() for d in range(NUM_DAYS)}
            for w in windows:
                if 0 <= w.day < NUM_DAYS:
                    for s in range(max(0, w.start_slot), min(NUM_SLOTS, w.end_slot)):
                        available_by_day[w.day].add(s)
            unavailable_by_day = {
                d: {s for s in range(NUM_SLOTS) if s not in available_by_day[d]}
                for d in range(NUM_DAYS)
            }
    return bookings, hard_ids, soft_ids, unavailable_by_day


def _should_merge_online_slot(group: list[Booking]) -> bool:
    if len(group) < 2:
        return False
    if not all(room_is_online(b.room) for b in group):
        return False
    staff_ids = {b.staff_id for b in group}
    return len(staff_ids) == 1


def _units_for_slot_group(group: list[Booking]) -> list[PrintPaintUnit]:
    if _should_merge_online_slot(group):
        return [PrintPaintUnit(tuple(group), "merged_online")]
    solos, pairs = _split_pairs(group)
    units: list[PrintPaintUnit] = []
    for t1_b, t2_b in pairs:
        units.append(PrintPaintUnit((t1_b, t2_b), "term_pair"))
    for b in solos:
        t1, t2 = _terms_of(b)
        if t1 and t2:
            units.append(PrintPaintUnit((b,), "full"))
        elif t1:
            units.append(PrintPaintUnit((b,), "t1_only"))
        elif t2:
            units.append(PrintPaintUnit((b,), "t2_only"))
    return units


def staff_timetable_lines(
    b: Booking,
    *,
    view_staff_id: int | None = None,
    term: PrintTerm | None = None,
) -> list[str]:
    from ..core.booking_staff import has_sfs_co_teacher
    from ..core.booking_sessions import format_session_weeks_label

    lines: list[str] = []
    title = _class_title_line(b)
    if title:
        lines.append(title)
    week_label = format_session_weeks_label(b, term=term)
    if week_label:
        lines.append(week_label)
    codes = _component_codes_line(b)
    if codes:
        lines.append(codes)
    room = (b.room.code if b.room else "") or ""
    if room:
        lines.append(room)
    grp = (b.course.code if b.course else "") or ""
    if grp:
        lines.append(grp)
    if has_sfs_co_teacher(b):
        co = getattr(b, "sfs_co_teacher", None)
        co_id = getattr(b, "sfs_co_teacher_staff_id", None)
        co_name = (co.name if co else "") or ""
        show_sfs = co_name and (
            view_staff_id is None
            or (b.staff_id == view_staff_id and co_id != view_staff_id)
        )
        if show_sfs:
            lines.append(f"SFS {co_name}")
    return lines


def print_card_lines_merged(
    group: list[Booking],
    kind: str,
    *,
    view_staff_id: int | None = None,
    term: PrintTerm | None = None,
) -> list[str]:
    term_kw = {"term": term} if term in ("t1", "t2") else {}
    if kind == "staff":
        lines = sorted({(b.course.code if b.course else "") or "" for b in group} - {""})
        rooms = sorted({(b.room.code if b.room else "") or "" for b in group} - {""})
        if len(rooms) == 1:
            lines.append(rooms[0])
        elif rooms:
            lines.append(", ".join(rooms))
        return lines

    lines: list[str] = []
    for b in sorted(group, key=lambda x: ((x.course.code if x.course else ""), x.id)):
        lines.extend(
            ln for ln in placecard_subject_block(b, **term_kw).split("\n") if ln.strip()
        )
    b0 = group[0]
    rooms = sorted({(b.room.code if b.room else "") or "" for b in group} - {""})
    if rooms:
        lines.append(", ".join(rooms))
    lec = export_lecturer_label(b0, **term_kw)
    if lec:
        lines.append(lec)
    if kind == "room":
        groups = sorted({(b.course.code if b.course else "") or "" for b in group} - {""})
        if groups:
            lines.append(", ".join(groups))
    return lines


def print_card_lines(
    b: Booking,
    kind: str,
    *,
    term: PrintTerm | None = None,
    view_staff_id: int | None = None,
) -> list[str]:
    term_kw = {"term": term} if term in ("t1", "t2") else {}
    if kind == "staff":
        return staff_timetable_lines(b, view_staff_id=view_staff_id, term=term)
    lines = [ln for ln in placecard_subject_block(b, **term_kw).split("\n") if ln.strip()]
    if kind == "course":
        room = (b.room.code if b.room else "") or ""
        if room:
            lines.append(room)
        lec = export_lecturer_label(b, **term_kw)
        if lec:
            lines.append(lec)
    else:
        lec = export_lecturer_label(b, **term_kw)
        if lec:
            lines.append(lec)
        grp = (b.course.code if b.course else "") or ""
        if grp:
            lines.append(grp)
    return [ln for ln in lines if ln]


def _lines_for_unit(
    unit: PrintPaintUnit,
    kind: str,
    *,
    view_staff_id: int | None,
    lane: PrintLane,
    term: PrintTerm | None,
) -> list[str]:
    if unit.term_layout == "merged_online":
        return print_card_lines_merged(
            list(unit.bookings), kind, view_staff_id=view_staff_id
        )
    b = unit.bookings[0]
    t: PrintTerm | None = term
    if unit.term_layout == "term_pair":
        if lane == "left":
            b = unit.bookings[0]
            t = "t1"
        else:
            b = unit.bookings[1]
            t = "t2"
    elif unit.term_layout == "t1_only":
        t = "t1"
    elif unit.term_layout == "t2_only":
        t = "t2"
    return print_card_lines(b, kind, term=t, view_staff_id=view_staff_id)


def build_print_page(
    session: Session,
    *,
    week_id: int,
    kind: PrintKind,
    entity_id: int,
    label: str,
    term_filter: str,
    colour_by_class: bool,
    violations_cache: list | None = None,
    colour_map: dict[str, str] | None = None,
) -> TimetablePrintPage:
    bookings, hard_ids, soft_ids, unavailable = load_entity_bookings(
        session,
        week_id=week_id,
        kind=kind,
        entity_id=entity_id,
        term_filter=term_filter,
        violations_cache=violations_cache,
    )
    fill_by_id = build_print_fill_by_booking_id(
        bookings,
        colour_by_class=colour_by_class,
        hard_ids=hard_ids,
        soft_ids=soft_ids,
        for_print=True,
        colour_map=colour_map,
    )
    view_staff_id = entity_id if kind == "staff" else None
    cards: list[PrintCardDraw] = []

    for slot_group in _bookings_by_slot(bookings):
        b0 = slot_group[0]
        units = _units_for_slot_group(slot_group)
        for sub_lane, unit in enumerate(units):
            lane: PrintLane
            if unit.term_layout == "term_pair":
                for lane_name in ("left", "right"):
                    lines = _lines_for_unit(
                        unit, kind, view_staff_id=view_staff_id, lane=lane_name, term=None
                    )
                    bid = unit.bookings[0].id if lane_name == "left" else unit.bookings[1].id
                    cards.append(
                        PrintCardDraw(
                            day=b0.day,
                            start_slot=b0.start_slot,
                            end_slot=b0.end_slot,
                            sub_lane=sub_lane,
                            sub_lane_count=len(units),
                            lane=lane_name,
                            lines=tuple(lines),
                            fill_hex=fill_by_id.get(bid, "#e5e7eb"),
                            booking_id=bid,
                            violation=violation_kind_for_booking(
                                bid, hard_ids=hard_ids, soft_ids=soft_ids
                            ),
                        )
                    )
                continue
            if unit.term_layout == "full":
                lane = "full"
            elif unit.term_layout == "t1_only":
                lane = "left"
            elif unit.term_layout == "t2_only":
                lane = "right"
            else:
                lane = "full"
            lines = _lines_for_unit(
                unit, kind, view_staff_id=view_staff_id, lane=lane, term=None
            )
            bid = unit.bookings[0].id
            cards.append(
                PrintCardDraw(
                    day=b0.day,
                    start_slot=b0.start_slot,
                    end_slot=b0.end_slot,
                    sub_lane=sub_lane,
                    sub_lane_count=len(units),
                    lane=lane,
                    lines=tuple(lines),
                    fill_hex=fill_by_id.get(bid, "#e5e7eb"),
                    booking_id=bid,
                    violation=violation_kind_for_booking(
                        bid, hard_ids=hard_ids, soft_ids=soft_ids
                    ),
                )
            )

    return TimetablePrintPage(
        headline=headline_for(kind, label),
        kind=kind,
        cards=tuple(cards),
        unavailable_by_day=unavailable,
    )


def collect_print_colour_map(
    session: Session,
    *,
    week_id: int,
    kind: PrintKind,
    entity_ids: list[int],
    term_filter: str,
    colour_by_class: bool,
    violations_cache: list | None = None,
) -> dict[str, str]:
    """One class→colour map for an entire print job (stable across all pages)."""
    specs = [PrintEntitySpec(kind=kind, entity_id=eid, label="") for eid in entity_ids]
    return collect_print_colour_map_for_entities(
        session,
        week_id=week_id,
        entities=specs,
        term_filter=term_filter,
        colour_by_class=colour_by_class,
        violations_cache=violations_cache,
    )


def collect_print_colour_map_for_entities(
    session: Session,
    *,
    week_id: int,
    entities: list[PrintEntitySpec],
    term_filter: str,
    colour_by_class: bool,
    violations_cache: list | None = None,
) -> dict[str, str]:
    """Stable class→colour map across mixed course/staff/room pages."""
    keys: set[str] = set()
    for spec in entities:
        bookings, _, _, _ = load_entity_bookings(
            session,
            week_id=week_id,
            kind=spec.kind,
            entity_id=spec.entity_id,
            term_filter=term_filter,
            violations_cache=violations_cache,
        )
        keys.update(collect_print_tint_keys(bookings, colour_by_class=colour_by_class))
    return assign_print_colours(keys)


def list_print_entities(
    session: Session,
    *,
    timetable_session_id: int,
    kind: PrintJobKind,
) -> list[PrintEntitySpec]:
    from ..core.sidebar_order import ordered_courses, ordered_staff

    if kind == "course":
        rows = ordered_courses(session, include_block_cohorts=True, timetable_session_id=timetable_session_id)
        return [PrintEntitySpec(kind="course", entity_id=c.id, label=c.code) for c in rows]
    if kind == "staff":
        rows = ordered_staff(session, timetable_session_id=timetable_session_id)
        return [PrintEntitySpec(kind="staff", entity_id=s.id, label=s.name or "(unnamed)") for s in rows]
    if kind == "course_staff":
        return list_print_entities(
            session, timetable_session_id=timetable_session_id, kind="course"
        ) + list_print_entities(session, timetable_session_id=timetable_session_id, kind="staff")
    if kind == "changed_courses":
        from ..core.change_log_data import affected_course_ids_from_resolved_changelog

        affected = affected_course_ids_from_resolved_changelog(
            session, timetable_session_id=timetable_session_id
        )
        rows = ordered_courses(
            session, include_block_cohorts=True, timetable_session_id=timetable_session_id
        )
        return [
            PrintEntitySpec(kind="course", entity_id=c.id, label=c.code)
            for c in rows
            if c.id in affected
        ]
    rows = (
        session.query(Room)
        .filter(Room.timetable_session_id == timetable_session_id)
        .order_by(Room.code)
        .all()
    )
    return [PrintEntitySpec(kind="room", entity_id=r.id, label=r.code) for r in rows]

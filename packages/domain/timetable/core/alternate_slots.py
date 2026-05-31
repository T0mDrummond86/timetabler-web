"""Find valid alternate day / time / room / lecturer placements for a booking."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby
from types import SimpleNamespace

from sqlalchemy.orm import Session

from ..constants import DAYS, NUM_DAYS, NUM_SLOTS, slot_to_time
from .booking_staff import staff_ids_with_term_overlap
from .models import (
    Booking,
    QualificationTimeWindow,
    Room,
    Staff,
    StaffAvailability,
    StaffCompetency,
    UnitAllowedRoom,
)
from .validation import (
    _overlap,
    permitted_parallel_online_cohort_overlap,
    _room_counts_for_physical_double_booking,
    _terms_overlap,
)


@dataclass(frozen=True)
class AlternatePlacement:
    day: int
    start_slot: int
    end_slot: int
    staff_id: int | None
    room_id: int | None

    @property
    def time_label(self) -> str:
        start = slot_to_time(self.start_slot).strftime("%H:%M")
        end = "22:00" if self.end_slot >= NUM_SLOTS else slot_to_time(self.end_slot).strftime("%H:%M")
        return f"{start}–{end}"

    def room_label(self, *, room_code: str) -> str:
        return room_code


@dataclass
class _PlacementProbe:
    """Hypothetical booking position used for constraint checks."""

    source: Booking
    day: int
    start_slot: int
    end_slot: int
    staff_id: int | None
    room_id: int | None

    @property
    def id(self) -> int:
        return self.source.id

    @property
    def week_id(self) -> int:
        return self.source.week_id

    @property
    def course_id(self) -> int:
        return self.source.course_id

    @property
    def unit_id(self) -> int | None:
        return self.source.unit_id

    @property
    def course(self):
        return self.source.course

    @property
    def unit(self):
        return self.source.unit

    @property
    def in_term_1(self):
        return getattr(self.source, "in_term_1", 1)

    @property
    def in_term_2(self):
        return getattr(self.source, "in_term_2", 1)

    @property
    def sfs_co_teacher_staff_id(self) -> int | None:
        return getattr(self.source, "sfs_co_teacher_staff_id", None)


def alternate_placements_by_day(
    session: Session,
    booking: Booking,
    week_bookings: list[Booking],
    *,
    times_only: bool = False,
    fixed_room_id: int | None = None,
    lock_staff: bool = False,
) -> dict[int, list[AlternatePlacement]]:
    """Map weekday index → valid (time, room, lecturer) placements."""
    duration = booking.end_slot - booking.start_slot
    if duration <= 0 or duration > NUM_SLOTS:
        return {}

    # Use every class in the week so room/staff clashes are detected across courses.
    others = [b for b in week_bookings if b.id != booking.id]
    ctx = _ConstraintContext.load(session, others)
    staff_ids = _candidate_staff_ids(booking, ctx, lock_staff=lock_staff)
    room_ids = _candidate_room_ids(booking, ctx, fixed_room_id=fixed_room_id)

    by_day: dict[int, list[AlternatePlacement]] = {}
    days = [booking.day] if times_only else list(range(NUM_DAYS))

    for day in days:
        options: list[AlternatePlacement] = []
        seen: set[tuple[int, int | None, int | None]] = set()
        for start in range(0, NUM_SLOTS - duration + 1):
            end = start + duration
            for staff_id in staff_ids:
                if not _staff_free_at(
                    booking, day, start, end, staff_id, others, ctx
                ):
                    continue
                for room_id in room_ids:
                    if not _room_free_at(
                        booking, day, start, end, room_id, others, ctx
                    ):
                        continue
                    if (
                        day == booking.day
                        and start == booking.start_slot
                        and staff_id == booking.staff_id
                        and room_id == booking.room_id
                    ):
                        continue
                    key = (start, staff_id, room_id)
                    if key in seen:
                        continue
                    probe = _PlacementProbe(
                        booking, day, start, end, staff_id, room_id
                    )
                    if _placement_is_valid(probe, others, ctx):
                        seen.add(key)
                        options.append(
                            AlternatePlacement(day, start, end, staff_id, room_id)
                        )
        if options:
            options.sort(
                key=lambda p: (p.start_slot, p.room_id or 0, p.staff_id or 0)
            )
            by_day[day] = options
    return by_day


def available_rooms_at_current_slot(
    session: Session,
    booking: Booking,
    week_bookings: list[Booking],
) -> list[int]:
    """Room ids free at this booking's current day and time (lecturer unchanged)."""
    others = [b for b in week_bookings if b.id != booking.id]
    ctx = _ConstraintContext.load(session, others)
    day = booking.day
    start = booking.start_slot
    end = booking.end_slot
    staff_id = booking.staff_id

    available: list[int] = []
    for room_id in _candidate_room_ids(booking, ctx, fixed_room_id=None):
        if room_id is None:
            continue
        probe = _PlacementProbe(booking, day, start, end, staff_id, room_id)
        if not _placement_is_valid(probe, others, ctx):
            continue
        available.append(room_id)

    available.sort(
        key=lambda rid: _room_display_code(ctx.rooms_by_id.get(rid)).lower()
    )
    return available


def build_available_rooms_menu(
    menu,
    session: Session,
    booking: Booking,
    week_bookings: list[Booking],
    *,
    on_pick,
) -> None:
    """Submenu of rooms free at the booking's current day and time."""
    from PySide6.QtGui import QAction

    ctx = _ConstraintContext.load(
        session, [b for b in week_bookings if b.id != booking.id]
    )
    room_ids = available_rooms_at_current_slot(session, booking, week_bookings)
    rooms_menu = menu.addMenu("Available rooms…")

    if not room_ids:
        empty = QAction("(No rooms free at this time)", rooms_menu)
        empty.setEnabled(False)
        rooms_menu.addAction(empty)
        return

    day_label = DAYS[booking.day]
    time_start = slot_to_time(booking.start_slot).strftime("%H:%M")
    time_end = (
        "22:00"
        if booking.end_slot >= NUM_SLOTS
        else slot_to_time(booking.end_slot).strftime("%H:%M")
    )
    rooms_menu.setToolTip(f"{day_label} {time_start}–{time_end}")

    for room_id in room_ids:
        room = ctx.rooms_by_id.get(room_id)
        label = _room_display_code(room)
        if room_id == booking.room_id:
            label = f"{label}  ◆"
        act = QAction(label, rooms_menu)
        act.triggered.connect(
            lambda _checked=False, rid=room_id: on_pick(
                booking.day, booking.start_slot, booking.staff_id, rid
            )
        )
        rooms_menu.addAction(act)


def alternate_slots_by_day(
    session: Session,
    booking: Booking,
    week_bookings: list[Booking],
    *,
    times_only: bool = False,
    fixed_room_id: int | None = None,
    lock_staff: bool = False,
) -> dict[int, list[AlternatePlacement]]:
    return alternate_placements_by_day(
        session,
        booking,
        week_bookings,
        times_only=times_only,
        fixed_room_id=fixed_room_id,
        lock_staff=lock_staff,
    )


@dataclass
class _ConstraintContext:
    staff_availability: dict[int, list[StaffAvailability]]
    qual_windows: dict[int, list[tuple[int, int, int]]]
    allowed_rooms_by_unit: dict[int, set[int]]
    allowed_staff_by_unit: dict[int, set[int]]
    rooms_by_id: dict[int, Room]
    staff_by_id: dict[int, Staff]

    @classmethod
    def load(cls, session: Session, week_bookings: list[Booking]) -> _ConstraintContext:
        staff_availability: dict[int, list[StaffAvailability]] = defaultdict(list)
        for row in session.query(StaffAvailability).all():
            staff_availability[row.staff_id].append(row)

        qual_windows: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
        for w in session.query(QualificationTimeWindow).all():
            qual_windows[w.qualification_id].append((w.day, w.start_slot, w.end_slot))

        allowed_rooms_by_unit: dict[int, set[int]] = defaultdict(set)
        for unit_id, room_id in session.query(
            UnitAllowedRoom.unit_id, UnitAllowedRoom.room_id
        ).all():
            allowed_rooms_by_unit[unit_id].add(room_id)

        allowed_staff_by_unit: dict[int, set[int]] = defaultdict(set)
        for staff_id, unit_id in session.query(
            StaffCompetency.staff_id, StaffCompetency.unit_id
        ).all():
            allowed_staff_by_unit[unit_id].add(staff_id)

        rooms_by_id = {r.id: r for r in session.query(Room).all()}
        staff_by_id = {s.id: s for s in session.query(Staff).all()}

        return cls(
            staff_availability=dict(staff_availability),
            qual_windows=dict(qual_windows),
            allowed_rooms_by_unit=dict(allowed_rooms_by_unit),
            allowed_staff_by_unit=dict(allowed_staff_by_unit),
            rooms_by_id=rooms_by_id,
            staff_by_id=staff_by_id,
        )


def _candidate_staff_ids(booking: Booking, ctx: _ConstraintContext, **_) -> list[int | None]:
    """Alternate moves always keep the assigned lecturer."""
    return [booking.staff_id]


def _booking_delivery_type(booking: Booking, ctx: _ConstraintContext) -> str:
    from .room_types import ROOM_TYPE_ON_CAMPUS, room_delivery_type

    if booking.room_id is not None:
        room = ctx.rooms_by_id.get(booking.room_id)
        if room is not None:
            return room_delivery_type(room)
    return ROOM_TYPE_ON_CAMPUS


def _room_matches_booking_delivery(
    booking: Booking, room: Room, ctx: _ConstraintContext
) -> bool:
    from .room_types import room_delivery_type

    return room_delivery_type(room) == _booking_delivery_type(booking, ctx)


def _candidate_room_ids(
    booking: Booking,
    ctx: _ConstraintContext,
    *,
    fixed_room_id: int | None,
) -> list[int | None]:
    """Rooms to try — same delivery type as current room, plus class constraints."""
    if fixed_room_id is not None:
        candidates = [fixed_room_id]
    elif booking.unit_id and (
        allowed := ctx.allowed_rooms_by_unit.get(booking.unit_id)
    ):
        candidates = list(allowed)
    else:
        candidates = [
            rid
            for rid, room in ctx.rooms_by_id.items()
            if _room_matches_booking_delivery(booking, room, ctx)
        ]

    out: list[int | None] = []
    for rid in candidates:
        if rid is None:
            continue
        room = ctx.rooms_by_id.get(rid)
        if room is None:
            continue
        if not _room_matches_booking_delivery(booking, room, ctx):
            continue
        if _room_satisfies_unit(booking, room):
            out.append(rid)

    # Scheduled classes keep a room; do not offer "no room" alternatives.
    if booking.room_id is not None:
        if booking.room_id not in out and booking.room_id in ctx.rooms_by_id:
            out.insert(0, booking.room_id)
        return out

    if not out:
        return [None]
    return out


def _room_display_code(room: Room | None) -> str:
    if room is None:
        return "—"
    return (room.code or room.name or f"Room {room.id}").strip() or "—"


def _room_satisfies_unit(booking: Booking, room: Room) -> bool:
    unit = booking.unit
    if unit is None:
        return True
    if unit.required_capacity and room.capacity and room.capacity < unit.required_capacity:
        return False
    from .room_types import room_types_match

    if unit.required_room_type and not room_types_match(
        unit.required_room_type, room.room_type
    ):
        return False
    return True


def _staff_free_at(
    booking: Booking,
    day: int,
    start_slot: int,
    end_slot: int,
    staff_id: int | None,
    others: list[Booking],
    ctx: _ConstraintContext,
) -> bool:
    if staff_id is None:
        return True
    probe = _PlacementProbe(booking, day, start_slot, end_slot, staff_id, booking.room_id)
    for other in others:
        if other.day != day:
            continue
        if not _overlap(start_slot, end_slot, other.start_slot, other.end_slot):
            continue
        if not _terms_overlap(booking, other):
            continue
        if _probe_clashes_staff(probe, other, ctx):
            return False
    return True


def _room_free_at(
    booking: Booking,
    day: int,
    start_slot: int,
    end_slot: int,
    room_id: int | None,
    others: list[Booking],
    ctx: _ConstraintContext,
) -> bool:
    if room_id is None:
        return True
    room = ctx.rooms_by_id.get(room_id)
    if room is None:
        return False
    if not _room_counts_for_physical_double_booking(room):
        return True
    for other in others:
        if other.id == booking.id or other.day != day:
            continue
        if other.room_id != room_id:
            continue
        if not _overlap(start_slot, end_slot, other.start_slot, other.end_slot):
            continue
        if not _terms_overlap(booking, other):
            continue
        return False
    return True


def _course_free_at(
    booking: Booking,
    day: int,
    start_slot: int,
    end_slot: int,
    others: list[Booking],
) -> bool:
    for other in others:
        if other.course_id != booking.course_id or other.day != day:
            continue
        if _overlap(start_slot, end_slot, other.start_slot, other.end_slot):
            return False
    return True


def _placement_is_valid(
    probe: _PlacementProbe,
    others: list[Booking],
    ctx: _ConstraintContext,
) -> bool:
    if probe.room_id is None and probe.source.room_id is not None:
        return False
    if probe.staff_id is None and probe.source.staff_id is not None:
        return False
    if not _fits_qualification_window(probe, ctx):
        return False
    if not _fits_staff_availability(probe, ctx):
        return False
    if not _fits_room_assignment(probe, ctx):
        return False
    if probe.staff_id is not None and not _staff_allowed_for_unit(probe, ctx):
        return False
    if not _course_free_at(
        probe.source, probe.day, probe.start_slot, probe.end_slot, others
    ):
        return False
    if not _staff_free_at(
        probe.source,
        probe.day,
        probe.start_slot,
        probe.end_slot,
        probe.staff_id,
        others,
        ctx,
    ):
        return False
    if not _room_free_at(
        probe.source,
        probe.day,
        probe.start_slot,
        probe.end_slot,
        probe.room_id,
        others,
        ctx,
    ):
        return False
    return True


def _staff_allowed_for_unit(probe: _PlacementProbe, ctx: _ConstraintContext) -> bool:
    if not probe.unit_id or probe.staff_id is None:
        return True
    allowed = ctx.allowed_staff_by_unit.get(probe.unit_id)
    if not allowed:
        return True
    return probe.staff_id in allowed


def _probe_clashes_staff(
    probe: _PlacementProbe, other: Booking, ctx: _ConstraintContext
) -> bool:
    if probe.staff_id is None:
        return False

    adapter = SimpleNamespace(
        id=probe.id,
        staff_id=probe.staff_id,
        sfs_co_teacher_staff_id=probe.sfs_co_teacher_staff_id,
        in_term_1=probe.in_term_1,
        in_term_2=probe.in_term_2,
        unit_id=probe.unit_id,
        course_id=probe.course_id,
    )
    shared = staff_ids_with_term_overlap(adapter, other)
    if not shared:
        return False
    probe_room = (
        ctx.rooms_by_id.get(probe.room_id) if probe.room_id is not None else None
    )
    other_room = getattr(other, "room", None)
    if other_room is None and other.room_id is not None:
        other_room = ctx.rooms_by_id.get(other.room_id)
    if permitted_parallel_online_cohort_overlap(
        adapter, other, a_room=probe_room, b_room=other_room
    ):
        return False
    return True


def _fits_qualification_window(probe: _PlacementProbe, ctx: _ConstraintContext) -> bool:
    if not (probe.course and probe.course.qualification_id):
        return True
    qwindows = ctx.qual_windows.get(probe.course.qualification_id)
    if not qwindows:
        return True
    return any(
        d == probe.day
        and s <= probe.start_slot
        and e >= probe.end_slot
        for d, s, e in qwindows
    )


def _fits_staff_availability(probe: _PlacementProbe, ctx: _ConstraintContext) -> bool:
    """Staff must be free in their availability grid when one is configured."""
    staff_ids_to_check: list[int] = []
    if probe.staff_id is not None:
        staff_ids_to_check.append(probe.staff_id)
    co_id = probe.sfs_co_teacher_staff_id
    if co_id is not None and co_id != probe.staff_id:
        staff_ids_to_check.append(co_id)

    for sid in staff_ids_to_check:
        windows = ctx.staff_availability.get(sid)
        if not windows:
            # No grid on file: only the lecturer already on this class is trusted.
            if sid not in (
                probe.source.staff_id,
                probe.sfs_co_teacher_staff_id,
            ):
                return False
            continue
        if not any(
            w.day == probe.day
            and w.start_slot <= probe.start_slot
            and w.end_slot >= probe.end_slot
            for w in windows
        ):
            return False
    return True


def _fits_room_assignment(probe: _PlacementProbe, ctx: _ConstraintContext) -> bool:
    if probe.room_id is None:
        return probe.source.room_id is None
    if probe.unit_id:
        allowed = ctx.allowed_rooms_by_unit.get(probe.unit_id)
        if allowed and probe.room_id not in allowed:
            return False
    room = ctx.rooms_by_id.get(probe.room_id)
    if room is None:
        return False
    return _room_satisfies_unit(probe.source, room)


def build_alternate_slots_menu(
    menu,
    session: Session,
    booking: Booking,
    week_bookings: list[Booking],
    *,
    times_only: bool,
    fixed_room_id: int | None,
    lock_staff: bool,
    on_pick,
) -> None:
    """Day → time → room submenus (lecturer unchanged)."""
    from PySide6.QtGui import QAction

    ctx = _ConstraintContext.load(session, week_bookings)
    by_day = alternate_placements_by_day(
        session,
        booking,
        week_bookings,
        times_only=times_only,
        fixed_room_id=fixed_room_id,
        lock_staff=lock_staff,
    )
    move_menu = menu.addMenu("Move to alternate slot…")

    if not by_day:
        empty = QAction("(No open slots)", move_menu)
        empty.setEnabled(False)
        move_menu.addAction(empty)
        return

    current_day = booking.day
    current_start = booking.start_slot
    current_room_id = booking.room_id

    def _is_current_placement(day: int, start: int, room_id: int | None) -> bool:
        return (
            day == current_day
            and start == current_start
            and room_id == current_room_id
        )

    for day_idx in sorted(by_day):
        day_title = DAYS[day_idx]
        if day_idx == current_day:
            day_title = f"{day_title}  ◆"
        day_menu = move_menu.addMenu(day_title)

        placements = by_day[day_idx]
        for _start, group_iter in groupby(placements, key=lambda p: p.start_slot):
            group = list(group_iter)
            time_label = group[0].time_label
            slot_is_current = day_idx == current_day and _start == current_start
            if len(group) == 1:
                p = group[0]
                room_code = _room_display_code(
                    ctx.rooms_by_id.get(p.room_id) if p.room_id else None
                )
                label = f"{time_label} — {p.room_label(room_code=room_code)}"
                if _is_current_placement(p.day, p.start_slot, p.room_id):
                    label = f"{label}  ◆"
                act = QAction(label, day_menu)
                act.triggered.connect(
                    lambda _checked=False, pl=p: on_pick(
                        pl.day, pl.start_slot, pl.staff_id, pl.room_id
                    )
                )
                day_menu.addAction(act)
                continue
            time_title = time_label
            if slot_is_current:
                time_title = f"{time_title}  ◆"
            time_menu = day_menu.addMenu(time_title)
            for p in group:
                room_code = _room_display_code(
                    ctx.rooms_by_id.get(p.room_id) if p.room_id else None
                )
                label = p.room_label(room_code=room_code)
                if _is_current_placement(p.day, p.start_slot, p.room_id):
                    label = f"{label}  ◆"
                act = QAction(label, time_menu)
                act.setToolTip(f"{DAYS[day_idx]} {time_label} — {room_code}")
                act.triggered.connect(
                    lambda _checked=False, pl=p: on_pick(
                        pl.day, pl.start_slot, pl.staff_id, pl.room_id
                    )
                )
                time_menu.addAction(act)

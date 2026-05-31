"""Day × room usage grid for a block cohort during one semester week."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, joinedload

from .block_delivery import (
    block_week_index_for_semester_week,
    qualification_for_course,
)
from .models import Booking, Course, Room
from .room_types import room_is_physical
from .validation import Severity, validate_bookings


@dataclass(frozen=True)
class BlockWeekDayRoomCell:
    """One day/room cell in the block week usage grid."""

    status: str  # "empty" | "ok" | "clash"
    label: str
    tooltip: str


@dataclass(frozen=True)
class BlockWeekUsageGrid:
    """Rooms across the top, days down the side — clash summary for one block week."""

    title: str
    subtitle: str
    rooms: list[Room]
    cells: dict[tuple[int, int], BlockWeekDayRoomCell]  # (day_index, room_column)


def _clash_lines_for_booking(
    booking: Booking,
    violations_by_booking: dict[int, list],
    session: Session,
) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for v in violations_by_booking.get(booking.id, []):
        if v.severity != Severity.HARD:
            continue
        if v.code not in ("room_double_booking", "staff_double_booking"):
            continue
        if v.message in seen:
            continue
        seen.add(v.message)
        other_ids = [bid for bid in v.booking_ids if bid != booking.id]
        extra = ""
        if other_ids:
            other = session.get(Booking, other_ids[0])
            if other is not None:
                if v.code == "room_double_booking":
                    extra = f" — with {other.course.code if other.course else 'class'}"
                elif v.code == "staff_double_booking":
                    course = other.course.code if other.course else "class"
                    extra = f" — with {course}"
        if v.code == "staff_double_booking":
            lines.append(f"Lecturer clash{extra}")
        else:
            lines.append(f"Room clash{extra}")
    return lines


def build_block_week_usage_grid(
    session: Session,
    *,
    course_id: int,
    semester_week: int,
    week_id: int,
) -> BlockWeekUsageGrid | None:
    """Build the day × room clash grid for one block group and semester week."""
    from ..constants import DAYS, slot_to_time

    course = session.get(Course, course_id)
    if course is None:
        return None
    qual = qualification_for_course(course, session)
    block_week_index = block_week_index_for_semester_week(course, semester_week, qual)
    if block_week_index is None:
        return None

    rooms = [
        r
        for r in session.query(Room).order_by(Room.code).all()
        if room_is_physical(r)
    ]
    block_bookings = (
        session.query(Booking)
        .options(
            joinedload(Booking.course),
            joinedload(Booking.unit),
            joinedload(Booking.staff),
            joinedload(Booking.room),
        )
        .filter(
            Booking.week_id == week_id,
            Booking.course_id == course_id,
            Booking.block_week_index == block_week_index,
        )
        .all()
    )

    violations = validate_bookings(session, week_id)
    violations_by_booking: dict[int, list] = {}
    block_ids = {b.id for b in block_bookings}
    for v in violations:
        if not any(bid in block_ids for bid in v.booking_ids):
            continue
        for bid in v.booking_ids:
            if bid in block_ids:
                violations_by_booking.setdefault(bid, []).append(v)

    cells: dict[tuple[int, int], BlockWeekDayRoomCell] = {}
    for day_idx in range(len(DAYS)):
        for col_idx, room in enumerate(rooms):
            cells[(day_idx, col_idx)] = BlockWeekDayRoomCell(
                status="empty",
                label="",
                tooltip=f"{DAYS[day_idx]} — {room.code}: no block class",
            )

    for b in block_bookings:
        if b.room_id is None:
            continue
        col_idx = next((i for i, r in enumerate(rooms) if r.id == b.room_id), None)
        if col_idx is None:
            continue
        day_idx = b.day
        if not (0 <= day_idx < len(DAYS)):
            continue
        start = slot_to_time(b.start_slot).strftime("%H:%M")
        end = (
            slot_to_time(b.end_slot).strftime("%H:%M")
            if b.end_slot < 28
            else "22:00"
        )
        unit = (b.unit.name if b.unit else "").strip() or "Class"
        staff = b.staff.name if b.staff else "—"
        clash_lines = _clash_lines_for_booking(b, violations_by_booking, session)
        base_tip = (
            f"{DAYS[day_idx]} {start}–{end}\n"
            f"{unit}\n"
            f"Lecturer: {staff}\n"
            f"Room: {b.room.code if b.room else '—'}"
        )
        if clash_lines:
            label = clash_lines[0]
            if len(clash_lines) > 1:
                label += f" (+{len(clash_lines) - 1})"
            cells[(day_idx, col_idx)] = BlockWeekDayRoomCell(
                status="clash",
                label=label,
                tooltip=base_tip + "\n\n" + "\n".join(clash_lines),
            )
        else:
            cells[(day_idx, col_idx)] = BlockWeekDayRoomCell(
                status="ok",
                label="OK",
                tooltip=base_tip + "\n\nNo room or lecturer clash",
            )

    qual_label = qual.name if qual is not None else "—"
    return BlockWeekUsageGrid(
        title=f"{course.code} — semester week {semester_week} (block week {block_week_index})",
        subtitle=f"{qual_label} · click another green week cell to compare",
        rooms=rooms,
        cells=cells,
    )

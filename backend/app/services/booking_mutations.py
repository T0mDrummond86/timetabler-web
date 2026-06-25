"""Apply booking edits with snapshots, locks, and change-log entries."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session, joinedload

from timetable.constants import NUM_DAYS, NUM_SLOTS
from timetable.core.booking_locks import effective_lock_staff, effective_lock_time
from timetable.core.booking_snapshots import snapshot_bookings
from .violation_dismissals import clear_booking_dismissals
from timetable.core.changelog import booking_change_log_payload
from timetable.core.double_session import (
    double_session_same_day,
    scheduled_session_parts,
    session_part_durations,
    unit_has_double_session,
)
from timetable.core.models import Booking, ChangeLogEntry, Course, Semester, Unit, Week

from .timetable_grid import build_course_timetable, get_repeating_week
from .violation_cache import invalidate_session_violations


class BookingNotFoundError(LookupError):
    pass


class BookingLockedError(PermissionError):
    pass


class NoChangeError(ValueError):
    pass


# Distinct from ``None``: omitted patch fields keep their current value; explicit ``None`` clears.
UNSET = object()


def _resolve_patch_value(current, patch):
    return current if patch is UNSET else patch


def patch_kwargs_from_body(body) -> dict:
    """Map a booking patch request to ``patch_booking`` keyword args."""
    field_names = (
        "day",
        "start_slot",
        "end_slot",
        "notes",
        "staff_id",
        "room_id",
        "lock_time",
        "lock_staff",
        "unit_id",
        "external_id",
        "in_term_1",
        "in_term_2",
        "sfs_co_teacher_staff_id",
        "sfs_co_teacher_in_term_1",
        "sfs_co_teacher_in_term_2",
        "online_student_count",
    )
    return {
        name: getattr(body, name) if name in body.model_fields_set else UNSET
        for name in field_names
    }


def _booking_in_session(db: Session, booking_id: int, timetable_session_id: int) -> Booking:
    booking = (
        db.query(Booking)
        .options(
            joinedload(Booking.staff),
            joinedload(Booking.course),
            joinedload(Booking.unit),
            joinedload(Booking.room),
        )
        .filter(Booking.id == booking_id)
        .first()
    )
    if booking is None:
        raise BookingNotFoundError("Booking not found")

    week = db.get(Week, booking.week_id)
    if week is None:
        raise BookingNotFoundError("Booking not found")
    semester = db.get(Semester, week.semester_id)
    if semester is None or semester.timetable_session_id != timetable_session_id:
        raise BookingNotFoundError("Booking not found")
    course = booking.course or db.get(Course, booking.course_id)
    if course is None or course.timetable_session_id != timetable_session_id:
        raise BookingNotFoundError("Booking not found")
    return booking


def _apply_snapshots(db: Session, target: dict[int, dict | None]) -> None:
    for bid, state in target.items():
        existing = db.get(Booking, bid)
        if state is None:
            if existing is not None:
                db.delete(existing)
        elif existing is None:
            db.add(Booking(id=bid, **state))
        else:
            for key, value in state.items():
                setattr(existing, key, value)
    db.flush()


def _log_change(
    db: Session,
    *,
    timetable_session_id: int,
    action: str,
    header: str,
    before: dict[int, dict | None],
    after: dict[int, dict | None],
) -> None:
    description, details = booking_change_log_payload(db, before, after, header=header)
    db.add(
        ChangeLogEntry(
            timetable_session_id=timetable_session_id,
            action=action,
            description=description,
            details=json.dumps(details),
        )
    )


def _mutation_result(
    db: Session,
    *,
    timetable_session_id: int,
    course_id: int,
    header: str,
    before: dict[int, dict | None],
    after: dict[int, dict | None],
    action: str = "change",
) -> dict:
    _log_change(
        db,
        timetable_session_id=timetable_session_id,
        action=action,
        header=header,
        before=before,
        after=after,
    )
    db.commit()
    invalidate_session_violations(db, timetable_session_id)
    grid = build_course_timetable(
        db,
        timetable_session_id=timetable_session_id,
        course_id=course_id,
    )
    return {
        "grid": grid,
        "change": {
            "description": header,
            "before": {str(k): v for k, v in before.items()},
            "after": {str(k): v for k, v in after.items()},
        },
    }


def patch_booking(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
    course_id: int,
    day=UNSET,
    start_slot=UNSET,
    end_slot=UNSET,
    notes=UNSET,
    staff_id=UNSET,
    room_id=UNSET,
    lock_time=UNSET,
    lock_staff=UNSET,
    unit_id=UNSET,
    external_id=UNSET,
    in_term_1=UNSET,
    in_term_2=UNSET,
    sfs_co_teacher_staff_id=UNSET,
    sfs_co_teacher_in_term_1=UNSET,
    sfs_co_teacher_in_term_2=UNSET,
    online_student_count=UNSET,
    header: str = "Edit booking",
) -> dict:
    booking = _booking_in_session(db, booking_id, timetable_session_id)
    staff = booking.staff
    course = booking.course

    time_locked = effective_lock_time(booking, staff=staff, course=course)
    staff_locked = effective_lock_staff(booking, staff=staff, course=course)

    new_day = _resolve_patch_value(booking.day, day)
    new_start = _resolve_patch_value(booking.start_slot, start_slot)
    new_end = _resolve_patch_value(booking.end_slot, end_slot)
    new_notes = _resolve_patch_value(booking.notes, notes)
    new_staff_id = _resolve_patch_value(booking.staff_id, staff_id)
    new_room_id = _resolve_patch_value(booking.room_id, room_id)
    new_lock_time = _resolve_patch_value(booking.lock_time, lock_time)
    new_lock_staff = _resolve_patch_value(booking.lock_staff, lock_staff)
    new_unit_id = _resolve_patch_value(booking.unit_id, unit_id)
    new_external_id = _resolve_patch_value(booking.external_id, external_id)
    new_in_term_1 = _resolve_patch_value(booking.in_term_1, in_term_1)
    new_in_term_2 = _resolve_patch_value(booking.in_term_2, in_term_2)
    new_co_id = _resolve_patch_value(booking.sfs_co_teacher_staff_id, sfs_co_teacher_staff_id)
    new_co_t1 = _resolve_patch_value(booking.sfs_co_teacher_in_term_1, sfs_co_teacher_in_term_1)
    new_co_t2 = _resolve_patch_value(booking.sfs_co_teacher_in_term_2, sfs_co_teacher_in_term_2)
    new_online = _resolve_patch_value(booking.online_student_count, online_student_count)

    if sfs_co_teacher_staff_id is not UNSET and new_co_id is None:
        new_co_t1 = 0
        new_co_t2 = 0

    if new_day < 0 or new_day >= NUM_DAYS:
        raise ValueError(f"day must be 0–{NUM_DAYS - 1}")
    if new_start < 0 or new_end > NUM_SLOTS or new_end <= new_start:
        raise ValueError("Invalid slot range")
    if not new_in_term_1 and not new_in_term_2:
        raise ValueError("Booking must be active in at least one term")

    time_changed = (
        new_day != booking.day
        or new_start != booking.start_slot
        or new_end != booking.end_slot
    )
    staff_changed = new_staff_id != booking.staff_id

    if time_locked and time_changed:
        raise BookingLockedError("This class's timeslot is locked and cannot be moved.")
    if staff_locked and staff_changed:
        raise BookingLockedError("This class's lecturer is locked and cannot be changed.")

    if (
        not time_changed
        and not staff_changed
        and new_room_id == booking.room_id
        and new_notes == booking.notes
        and new_lock_time == booking.lock_time
        and new_lock_staff == booking.lock_staff
        and new_unit_id == booking.unit_id
        and new_external_id == booking.external_id
        and new_in_term_1 == booking.in_term_1
        and new_in_term_2 == booking.in_term_2
        and new_co_id == booking.sfs_co_teacher_staff_id
        and new_co_t1 == booking.sfs_co_teacher_in_term_1
        and new_co_t2 == booking.sfs_co_teacher_in_term_2
        and new_online == booking.online_student_count
    ):
        raise NoChangeError("No changes")

    before = snapshot_bookings(db, [booking_id])
    booking.day = new_day
    booking.start_slot = new_start
    booking.end_slot = new_end
    booking.notes = new_notes
    booking.staff_id = new_staff_id
    booking.room_id = new_room_id
    booking.lock_time = new_lock_time
    booking.lock_staff = new_lock_staff
    booking.unit_id = new_unit_id
    booking.external_id = new_external_id
    booking.in_term_1 = new_in_term_1
    booking.in_term_2 = new_in_term_2
    booking.sfs_co_teacher_staff_id = new_co_id
    booking.sfs_co_teacher_in_term_1 = new_co_t1
    booking.sfs_co_teacher_in_term_2 = new_co_t2
    booking.online_student_count = new_online
    clear_booking_dismissals(db, timetable_session_id=timetable_session_id, booking_ids=[booking_id])
    db.flush()
    after = snapshot_bookings(db, [booking_id])
    return _mutation_result(
        db,
        timetable_session_id=timetable_session_id,
        course_id=course_id,
        header=header,
        before=before,
        after=after,
    )


def move_booking(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
    course_id: int,
    day: int,
    start_slot: int,
    room_id=UNSET,
) -> dict:
    booking = _booking_in_session(db, booking_id, timetable_session_id)
    if effective_lock_time(booking, staff=booking.staff, course=booking.course):
        raise BookingLockedError("This class's timeslot is locked and cannot be moved.")

    duration = booking.end_slot - booking.start_slot
    new_start = max(0, min(start_slot, NUM_SLOTS - duration))
    new_room_id = _resolve_patch_value(booking.room_id, room_id)
    if (
        booking.day == day
        and booking.start_slot == new_start
        and new_room_id == booking.room_id
    ):
        raise NoChangeError("No changes")

    patch_kwargs: dict = dict(
        day=day,
        start_slot=new_start,
        end_slot=new_start + duration,
    )
    if room_id is not UNSET:
        patch_kwargs["room_id"] = room_id

    return patch_booking(
        db,
        timetable_session_id=timetable_session_id,
        booking_id=booking_id,
        course_id=course_id,
        header="Move booking",
        **patch_kwargs,
    )


def restore_booking_snapshots(
    db: Session,
    *,
    timetable_session_id: int,
    course_id: int,
    snapshots: dict[int, dict | None],
    action: str,
    label: str,
) -> dict:
    if action not in ("undo", "redo"):
        raise ValueError("action must be undo or redo")

    booking_ids = list(snapshots.keys())
    for bid in booking_ids:
        _booking_in_session(db, bid, timetable_session_id)

    before = snapshot_bookings(db, booking_ids)
    _apply_snapshots(db, snapshots)
    after = snapshot_bookings(db, booking_ids)
    header = f"{'Undo' if action == 'undo' else 'Redo'}: {label}"
    return _mutation_result(
        db,
        timetable_session_id=timetable_session_id,
        course_id=course_id,
        header=header,
        before=before,
        after=after,
        action=action,
    )


def create_booking(
    db: Session,
    *,
    timetable_session_id: int,
    course_id: int,
    unit_id: int,
    day: int,
    start_slot: int,
    end_slot: int,
    staff_id: int | None = None,
    room_id: int | None = None,
    session_part: int = 1,
    notes: str | None = None,
    block_week_index: int | None = None,
) -> dict:
    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.timetable_session_id == timetable_session_id)
        .first()
    )
    if course is None:
        raise BookingNotFoundError("Course not found")
    unit = (
        db.query(Unit)
        .filter(Unit.id == unit_id, Unit.timetable_session_id == timetable_session_id)
        .first()
    )
    if unit is None:
        raise BookingNotFoundError("Unit not found")
    if day < 0 or day >= NUM_DAYS:
        raise ValueError(f"day must be 0–{NUM_DAYS - 1}")

    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        raise RuntimeError("No repeating week for session")

    def _clamp_start(slot: int, duration: int) -> tuple[int, int]:
        start = max(0, min(slot, NUM_SLOTS - duration))
        return start, start + duration

    def _make(part: int, duration: int, d: int, slot: int) -> Booking:
        s, e = _clamp_start(slot, duration)
        b = Booking(
            week_id=week.id,
            course_id=course_id,
            unit_id=unit_id,
            staff_id=staff_id,
            room_id=room_id,
            day=d,
            start_slot=s,
            end_slot=e,
            session_part=part,
            notes=notes,
            in_term_1=1,
            in_term_2=1,
            block_week_index=block_week_index,
        )
        db.add(b)
        db.flush()
        return b

    created: list[Booking] = []
    if unit_has_double_session(unit):
        slots1, slots2 = session_part_durations(unit)
        existing = scheduled_session_parts(
            db,
            week.id,
            course_id,
            unit_id,
            block_week_index=block_week_index,
        )
        b1: Booking | None = None
        if 1 not in existing:
            b1 = _make(1, slots1, day, start_slot)
            created.append(b1)
        elif session_part == 1:
            b1 = (
                db.query(Booking)
                .filter(
                    Booking.week_id == week.id,
                    Booking.course_id == course_id,
                    Booking.unit_id == unit_id,
                    Booking.session_part == 1,
                    Booking.block_week_index == block_week_index
                    if block_week_index is not None
                    else Booking.block_week_index.is_(None),
                )
                .first()
            )
        if 2 not in existing:
            if double_session_same_day(unit) and b1 is not None:
                d2, s2 = day, b1.end_slot + 1
                if s2 + slots2 > NUM_SLOTS:
                    s2 = max(0, NUM_SLOTS - slots2)
            elif b1 is not None:
                d2, s2 = (day + 1) % NUM_DAYS, start_slot
            else:
                d2, s2 = (day + 1) % NUM_DAYS, start_slot
            created.append(_make(2, slots2, d2, s2))
    else:
        if start_slot < 0 or end_slot > NUM_SLOTS or end_slot <= start_slot:
            raise ValueError("Invalid slot range")
        created.append(_make(session_part, end_slot - start_slot, day, start_slot))

    if not created:
        raise NoChangeError("Class already fully scheduled")

    ids = [b.id for b in created]
    before = {bid: None for bid in ids}
    after = snapshot_bookings(db, ids)
    label = unit.name or "class"
    if len(created) > 1:
        label = f"{label} (double session)"
    return _mutation_result(
        db,
        timetable_session_id=timetable_session_id,
        course_id=course_id,
        header=f"Add {label}",
        before=before,
        after=after,
    )


def delete_booking(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
    course_id: int,
) -> dict:
    booking = _booking_in_session(db, booking_id, timetable_session_id)
    if effective_lock_time(booking, staff=booking.staff, course=booking.course):
        raise BookingLockedError("This class's timeslot is locked and cannot be removed.")
    before = snapshot_bookings(db, [booking_id])
    db.delete(booking)
    db.flush()
    after = snapshot_bookings(db, [booking_id])
    return _mutation_result(
        db,
        timetable_session_id=timetable_session_id,
        course_id=course_id,
        header="Delete booking",
        before=before,
        after=after,
    )

"""Semester schedule, block delivery panel, block overview, and usage grids."""
from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from timetable.constants import DAYS, NUM_SLOTS, slot_to_time
from timetable.core.block_delivery import (
    all_block_overview_rows,
    block_qualification_group_courses,
    course_block_start_semester_week,
    course_block_week_count,
    enable_block_delivery_mode,
    is_block_qualification,
    qualification_for_course,
)
from timetable.core.block_week_usage import build_block_week_usage_grid
from timetable.core.booking_sessions import (
    SEMESTER_WEEKS,
    active_session_weeks,
    full_session_weeks_for_booking,
    toggle_session_week,
)
from timetable.core.models import Booking, Qualification
from timetable.core.schedule_variants import (
    booking_owning_week,
    group_schedule_bookings,
    primary_booking,
)

from .timetable_grid import get_repeating_week


def _booking_row_label(b: Booking) -> str:
    unit = (b.unit.name if b.unit else "").strip() or f"Class #{b.unit_id or '?'}"
    day = DAYS[b.day] if 0 <= b.day < len(DAYS) else f"Day {b.day}"
    start = slot_to_time(b.start_slot).strftime("%H:%M")
    end_slot = b.end_slot
    end = slot_to_time(end_slot).strftime("%H:%M") if end_slot < NUM_SLOTS else "22:00"
    part = f" (part {b.session_part})" if getattr(b, "session_part", 1) > 1 else ""
    ext = (b.external_id or "").strip()
    tag = f" [{ext}]" if ext else ""
    return f"{unit}{part}{tag} — {day} {start}–{end}"


def build_course_semester_schedule(
    db: Session,
    *,
    timetable_session_id: int,
    course_id: int,
    selected_semester_week: int | None = None,
) -> dict:
    from timetable.core.models import Course

    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.timetable_session_id == timetable_session_id)
        .first()
    )
    if course is None:
        raise LookupError("Course not found")

    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.unit))
        .filter(
            Booking.course_id == course_id,
            Booking.block_week_index.is_(None),
        )
        .order_by(Booking.unit_id, Booking.day, Booking.start_slot, Booking.session_part)
        .all()
    )
    groups = group_schedule_bookings(bookings)
    group_list = sorted(
        groups.values(),
        key=lambda g: (
            primary_booking(g).unit_id or 0,
            getattr(primary_booking(g), "session_part", 1) or 1,
            primary_booking(g).day,
            primary_booking(g).start_slot,
        ),
    )

    rows: list[dict] = []
    for group in group_list:
        primary = primary_booking(group)
        active_all: set[int] = set()
        allowed_all: set[int] = set()
        for b in group:
            active_all.update(active_session_weeks(b))
            allowed_all.update(full_session_weeks_for_booking(b))
        week_cells = []
        for week_num in range(1, SEMESTER_WEEKS + 1):
            owner = booking_owning_week(group, week_num)
            week_cells.append(
                {
                    "week": week_num,
                    "active": week_num in active_all,
                    "applicable": week_num in allowed_all,
                    "booking_id": owner.id,
                }
            )
        rows.append(
            {
                "primary_booking_id": primary.id,
                "label": _booking_row_label(primary),
                "has_variants": len(group) > 1,
                "weeks": week_cells,
            }
        )

    selected = selected_semester_week if selected_semester_week is not None else 1
    selected = max(1, min(SEMESTER_WEEKS, selected))

    return {
        "course_id": course_id,
        "course_code": course.code,
        "selected_semester_week": selected,
        "semester_weeks": SEMESTER_WEEKS,
        "rows": rows,
    }


def toggle_booking_session_week(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
    semester_week: int,
) -> dict:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise LookupError("Booking not found")
    week = get_repeating_week(db, timetable_session_id)
    if week is None or booking.week_id != week.id:
        raise LookupError("Booking not found")
    if booking.block_week_index is not None:
        raise ValueError("Cannot toggle semester weeks on block bookings")
    allowed = set(full_session_weeks_for_booking(booking))
    if semester_week not in allowed:
        raise ValueError("Week not applicable for this booking")
    toggle_session_week(booking, semester_week)
    db.flush()
    return build_course_semester_schedule(
        db,
        timetable_session_id=timetable_session_id,
        course_id=booking.course_id,
        selected_semester_week=semester_week,
    )


def build_block_delivery_panel(
    db: Session,
    *,
    timetable_session_id: int,
    qualification_id: int,
    course_id: int | None = None,
    block_week_index: int | None = None,
) -> dict:
    qual = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == timetable_session_id,
        )
        .first()
    )
    if qual is None:
        raise LookupError("Qualification not found")

    courses = block_qualification_group_courses(db, qual)
    if courses and not is_block_qualification(qual):
        enable_block_delivery_mode(db, qual)
        db.flush()
        qual = db.get(Qualification, qualification_id)
        courses = block_qualification_group_courses(db, qual)

    selected_course_id = course_id
    if selected_course_id is None and courses:
        selected_course_id = courses[0].id
    selected_course = next((c for c in courses if c.id == selected_course_id), None)

    week_count = 1
    start_week = 1
    if selected_course is not None:
        week_count = course_block_week_count(selected_course, qual)
        start_week = course_block_start_semester_week(selected_course, qual)

    idx = block_week_index if block_week_index is not None else 1
    idx = max(1, min(week_count or 1, idx))

    summary = "Not a block qualification."
    if is_block_qualification(qual):
        if not courses:
            summary = "No block groups yet. Create block groups on the Qualifications tab."
        elif selected_course is not None:
            summary = (
                f"{selected_course.code}: block weeks W{start_week}–"
                f"W{start_week + week_count - 1} ({week_count} week{'s' if week_count != 1 else ''})"
            )
        else:
            summary = "Select a block group."

    return {
        "qualification_id": qualification_id,
        "qualification_name": qual.name,
        "groups": [{"id": c.id, "code": c.code} for c in courses],
        "selected_course_id": selected_course_id,
        "block_week_count": week_count,
        "block_start_semester_week": start_week,
        "block_week_index": idx,
        "summary": summary,
    }


def build_block_overview(db: Session, *, timetable_session_id: int) -> dict:
    del timetable_session_id
    rows = all_block_overview_rows(db)
    return {
        "rows": [
            {
                "course_id": r.course_id,
                "label": r.label,
                "tooltip": r.tooltip,
                "calendar_weeks": list(r.calendar_weeks),
            }
            for r in rows
        ],
        "semester_weeks": SEMESTER_WEEKS,
    }


def build_block_week_usage(
    db: Session,
    *,
    timetable_session_id: int,
    course_id: int,
    semester_week: int,
) -> dict | None:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return None
    grid = build_block_week_usage_grid(
        db,
        course_id=course_id,
        semester_week=semester_week,
        week_id=week.id,
    )
    if grid is None:
        return None
    room_codes = [r.code for r in grid.rooms]
    cells: list[list[dict]] = []
    for day_idx in range(len(DAYS)):
        row: list[dict] = []
        for col_idx in range(len(grid.rooms)):
            cell = grid.cells.get((day_idx, col_idx))
            if cell is None:
                row.append({"status": "empty", "label": "", "tooltip": ""})
            else:
                row.append(
                    {
                        "status": cell.status,
                        "label": cell.label,
                        "tooltip": cell.tooltip,
                    }
                )
        cells.append(row)
    return {
        "title": grid.title,
        "subtitle": grid.subtitle,
        "rooms": room_codes,
        "days": list(DAYS),
        "cells": cells,
    }

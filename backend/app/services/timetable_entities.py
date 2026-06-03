"""Sidebar entity lists for each timetable view kind."""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.constants import DAYS
from timetable.core.block_delivery import DELIVERY_BLOCK, block_sidebar_label
from timetable.core.booking_staff import sfs_co_teacher_booking_filter
from timetable.core.models import Booking, Course, Qualification, Staff, Week
from timetable.core.pending_classes import pending_classes_for_week
from timetable.core.sidebar_order import ordered_courses, ordered_staff, set_course_sidebar_order, set_staff_sidebar_order
from timetable.core.staff_hours import safe_staff_tab_total_hours_by_staff_id
from timetable.core.unassigned_lecturer import bookings_without_lecturer

from .timetable_grid import count_bookings_on_day, get_repeating_week, scheduled_hours_on_day

_LOCK_PREFIX = "🔒 "


def list_timetable_entities(
    db: Session,
    *,
    timetable_session_id: int,
    view: str,
) -> list[dict]:
    """Return ``{id, label, entity_type}`` rows for the sidebar."""
    if view in ("course", "course_semester", "co_teach"):
        return _course_entities(db, timetable_session_id, view)
    if view == "block_delivery":
        return _block_qual_entities(db, timetable_session_id)
    if view == "block_overview":
        return [{"id": 0, "label": "All block groups", "entity_type": "block_overview"}]
    if view == "staff":
        return _staff_entities(db, timetable_session_id)
    if view in ("day", "room"):
        return _day_entities(db, timetable_session_id)
    if view == "unassigned_lecturer":
        return _unassigned_entities(db, timetable_session_id)
    raise ValueError(f"Unknown view kind: {view}")


def _course_entities(db: Session, timetable_session_id: int, view: str) -> list[dict]:
    courses = [
        c
        for c in ordered_courses(db)
        if c.timetable_session_id == timetable_session_id
    ]
    if view != "co_teach":
        return [
            {
                "id": c.id,
                "label": f"{_LOCK_PREFIX}{c.code}" if getattr(c, "timetable_locked", 0) else c.code,
                "entity_type": "course",
            }
            for c in courses
        ]

    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return []
    co_course_ids = {
        row[0]
        for row in db.query(Booking.course_id)
        .filter(Booking.week_id == week.id, sfs_co_teacher_booking_filter())
        .distinct()
        .all()
    }
    rows: list[dict] = []
    for c in courses:
        if c.id not in co_course_ids:
            continue
        n = (
            db.query(Booking)
            .filter(
                Booking.week_id == week.id,
                Booking.course_id == c.id,
                sfs_co_teacher_booking_filter(),
            )
            .count()
        )
        label = f"{c.code}  ·  {n} co-teach class{'es' if n != 1 else ''}"
        if getattr(c, "timetable_locked", 0):
            label = f"{_LOCK_PREFIX}{label}"
        rows.append({"id": c.id, "label": label, "entity_type": "co_teach"})
    return rows


def _block_qual_entities(db: Session, timetable_session_id: int) -> list[dict]:
    block_qual_ids = {
        row[0]
        for row in db.query(Course.qualification_id)
        .filter(
            Course.timetable_session_id == timetable_session_id,
            Course.qualification_id.isnot(None),
            Course.is_block_cohort == 1,
        )
        .distinct()
        .all()
        if row[0] is not None
    }
    quals = (
        db.query(Qualification)
        .filter(Qualification.timetable_session_id == timetable_session_id)
        .order_by(Qualification.name)
        .all()
    )
    rows: list[dict] = []
    for q in quals:
        is_block = getattr(q, "delivery_mode", None) == DELIVERY_BLOCK
        if not is_block and q.id not in block_qual_ids:
            continue
        rows.append(
            {
                "id": q.id,
                "label": block_sidebar_label(q, db),
                "entity_type": "block_qual",
            }
        )
    return rows


def _staff_entities(db: Session, timetable_session_id: int) -> list[dict]:
    hours_map = safe_staff_tab_total_hours_by_staff_id(db)
    staff = [s for s in ordered_staff(db) if s.timetable_session_id == timetable_session_id]
    rows: list[dict] = []
    for s in staff:
        h = hours_map.get(s.id, 0.0)
        label = f"{s.name}  ·  {h:.1f} h"
        if getattr(s, "timetable_locked", 0):
            label = f"{_LOCK_PREFIX}{label}"
        rows.append({"id": s.id, "label": label, "entity_type": "staff"})
    return rows


def _day_entities(db: Session, timetable_session_id: int) -> list[dict]:
    rows: list[dict] = []
    for d in range(len(DAYS)):
        n = count_bookings_on_day(db, timetable_session_id, d)
        hrs = scheduled_hours_on_day(db, timetable_session_id, d)
        rows.append(
            {
                "id": d,
                "label": f"{DAYS[d]}  ·  {n} class{'es' if n != 1 else ''}  ·  {hrs:.1f} h",
                "entity_type": "day",
            }
        )
    return rows


def _unassigned_entities(db: Session, timetable_session_id: int) -> list[dict]:
    week = get_repeating_week(db, timetable_session_id)
    if week is None:
        return [{"id": 0, "label": "Unassigned lecturer", "entity_type": "unassigned_lecturer"}]
    on_grid = len(bookings_without_lecturer(db, week.id))
    pending = len(pending_classes_for_week(db, week.id))
    return [
        {
            "id": 0,
            "label": (
                f"Unassigned lecturer  ·  {on_grid} on grid  ·  {pending} not scheduled"
            ),
            "entity_type": "unassigned_lecturer",
        }
    ]


def persist_sidebar_order(
    db: Session,
    *,
    timetable_session_id: int,
    view: str,
    entity_ids: list[int],
) -> None:
    if view == "course":
        courses = {
            c.id: c
            for c in db.query(Course)
            .filter(Course.timetable_session_id == timetable_session_id)
            .all()
        }
        valid = [cid for cid in entity_ids if cid in courses]
        set_course_sidebar_order(db, valid)
    elif view == "staff":
        staff_map = {
            s.id: s
            for s in db.query(Staff)
            .filter(Staff.timetable_session_id == timetable_session_id)
            .all()
        }
        valid = [sid for sid in entity_ids if sid in staff_map]
        set_staff_sidebar_order(db, valid)
    else:
        raise ValueError("Sidebar reorder only supported for course and staff views")

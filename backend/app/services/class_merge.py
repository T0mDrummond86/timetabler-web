"""Manually merge clashing classes on the lecturer view into one placecard.

A merge tags the clashing bookings with a shared ``manual_merge_group_id``.
This is independent of the auto-detected ``combined_class_group_id`` (so it
survives re-imports and combined-class re-scans) but is treated the same way
for staff hours and clash suppression (see core/combined_class.py).
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from timetable.core.models import Booking, Semester, Week

from .booking_mutations import _booking_in_session
from .violation_cache import invalidate_session_violations


def _session_week_ids(db: Session, timetable_session_id: int) -> list[int]:
    return [
        wid
        for (wid,) in db.query(Week.id)
        .join(Semester, Week.semester_id == Semester.id)
        .filter(Semester.timetable_session_id == timetable_session_id)
        .all()
    ]


def _next_group_id(db: Session, week_ids: list[int]) -> int:
    current = (
        db.query(func.max(Booking.manual_merge_group_id))
        .filter(Booking.week_id.in_(week_ids))
        .scalar()
    )
    return int(current or 0) + 1


def merge_classes(
    db: Session,
    *,
    timetable_session_id: int,
    booking_ids: list[int],
) -> dict:
    if len(booking_ids) < 2:
        raise ValueError("Select at least two classes to merge")

    bookings = [
        _booking_in_session(db, bid, timetable_session_id) for bid in dict.fromkeys(booking_ids)
    ]
    staff_ids = {b.staff_id for b in bookings}
    if len(staff_ids) != 1 or None in staff_ids:
        raise ValueError("Can only merge classes taught by the same lecturer")
    if len({b.day for b in bookings}) != 1:
        raise ValueError("Can only merge classes on the same day")
    if len({b.week_id for b in bookings}) != 1:
        raise ValueError("Can only merge classes in the same week")
    # Require a common overlapping instant (a genuine clash).
    if max(b.start_slot for b in bookings) >= min(b.end_slot for b in bookings):
        raise ValueError("These classes do not overlap")

    week_ids = _session_week_ids(db, timetable_session_id)
    existing = {b.manual_merge_group_id for b in bookings if b.manual_merge_group_id is not None}
    if existing:
        group_id = min(existing)
        # Fold any other already-merged groups into this one.
        if len(existing) > 1:
            db.query(Booking).filter(
                Booking.week_id.in_(week_ids),
                Booking.manual_merge_group_id.in_(existing),
            ).update({Booking.manual_merge_group_id: group_id}, synchronize_session=False)
    else:
        group_id = _next_group_id(db, week_ids)

    for b in bookings:
        b.manual_merge_group_id = group_id
    db.commit()
    invalidate_session_violations(db, timetable_session_id)
    return {"group_id": group_id, "merged": len(bookings)}


def unmerge_classes(
    db: Session,
    *,
    timetable_session_id: int,
    booking_id: int,
) -> dict:
    booking = _booking_in_session(db, booking_id, timetable_session_id)
    manual_id = booking.manual_merge_group_id
    combined_id = booking.combined_class_group_id
    if manual_id is None and combined_id is None:
        raise ValueError("This class is not part of a merge")
    week_ids = _session_week_ids(db, timetable_session_id)
    # Clear both the manual merge and (if present) the auto-detected combined
    # group, so unmerge works whether the card was merged by hand or detected.
    # An auto-detected combined class will re-merge on the next import re-scan.
    if manual_id is not None:
        db.query(Booking).filter(
            Booking.week_id.in_(week_ids),
            Booking.manual_merge_group_id == manual_id,
        ).update(
            {Booking.manual_merge_group_id: None, Booking.combined_class_group_id: None},
            synchronize_session=False,
        )
    if combined_id is not None:
        db.query(Booking).filter(
            Booking.week_id.in_(week_ids),
            Booking.combined_class_group_id == combined_id,
        ).update(
            {Booking.manual_merge_group_id: None, Booking.combined_class_group_id: None},
            synchronize_session=False,
        )
    db.commit()
    invalidate_session_violations(db, timetable_session_id)
    return {"ok": True}

"""Combine two qualifications into a new third one.

The inverse of ``qualification_stages`` in spirit, but not in mechanics, and
the difference is the whole design: a stage split *divides* one qualification
and rewrites its class links, whereas a merge *adds* a qualification and
rewrites nothing.

Both sources survive the merge untouched — same name, same groups, same
bookings, same class links. That is possible because a class may already
belong to several qualifications at once (see ``UnitQualification``), so the
new qualification simply links the union of the two class lists. Nothing is
moved, so nothing can be lost, and a merge on a fully timetabled session is
as safe as one on an empty one.

The new qualification gets its own cohorts, like any other. It is a real
qualification from the moment it exists, not a view over the two it came from,
and editing or deleting it later has no effect on its sources.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import (
    Booking,
    Course,
    Qualification,
    StaffQualificationOnlineStudents,
    Unit,
    UnitQualification,
)
from timetable.core.qualification_schedule import (
    normalize_schedule_period,
    replace_qualification_time_windows,
)

from .qualification_editor import sync_qualification_regular_groups

#: Matches the ceiling the qualification editor already enforces on num_groups.
MAX_GROUPS = 26


class QualificationMergeError(ValueError):
    """The merge cannot be performed; the message is meant for the user."""


def _load(db: Session, *, timetable_session_id: int, qualification_id: int) -> Qualification:
    qual = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == timetable_session_id,
        )
        .one_or_none()
    )
    if qual is None:
        raise LookupError(f"Qualification {qualification_id} not found")
    return qual


def _linked_unit_ids(db: Session, qualification_id: int) -> set[int]:
    return {
        uq.unit_id
        for uq in db.query(UnitQualification)
        .filter(UnitQualification.qualification_id == qualification_id)
        .all()
    }


def _booking_count(db: Session, qualification_id: int) -> int:
    """Bookings sitting on this qualification's cohorts.

    Reported so the dialog can say what is at stake, not to block anything —
    a merge never touches a source's cohorts, so bookings are never at risk.
    """
    course_ids = [
        c.id for c in db.query(Course).filter(Course.qualification_id == qualification_id).all()
    ]
    if not course_ids:
        return 0
    return db.query(Booking).filter(Booking.course_id.in_(course_ids)).count()


def suggested_merge_name(first: str, second: str) -> str:
    """A starting point for the name field, never the final word.

    Deliberately naive — the user renames it in the dialog. Anything cleverer
    (finding a common stem, stripping stage suffixes) guesses wrong often
    enough to be worse than an obvious join.
    """
    left, right = first.strip(), second.strip()
    if not left:
        return right or "Merged qualification"
    if not right:
        return left
    return f"{left} + {right}"


def merge_preview(
    db: Session,
    *,
    timetable_session_id: int,
    first_qualification_id: int,
    second_qualification_id: int,
) -> dict:
    """What the dialog needs to show before the user commits."""
    if first_qualification_id == second_qualification_id:
        raise QualificationMergeError("Pick two different qualifications to merge.")

    first = _load(
        db, timetable_session_id=timetable_session_id, qualification_id=first_qualification_id
    )
    second = _load(
        db, timetable_session_id=timetable_session_id, qualification_id=second_qualification_id
    )

    first_units = _linked_unit_ids(db, first.id)
    second_units = _linked_unit_ids(db, second.id)
    shared = first_units & second_units
    combined = first_units | second_units

    names = {
        u.id: u.name
        for u in db.query(Unit).filter(Unit.id.in_(combined)).all()
    } if combined else {}

    def side(qual: Qualification, unit_ids: set[int]) -> dict:
        return {
            "id": qual.id,
            "name": qual.name,
            "num_groups": qual.num_groups or 1,
            "schedule_period": normalize_schedule_period(qual.schedule_period),
            "delivery_mode": qual.delivery_mode or "regular",
            "class_count": len(unit_ids),
            "booking_count": _booking_count(db, qual.id),
        }

    warnings: list[str] = []
    if normalize_schedule_period(first.schedule_period) != normalize_schedule_period(
        second.schedule_period
    ):
        warnings.append(
            f"{first.name} is a {normalize_schedule_period(first.schedule_period)} "
            f"qualification and {second.name} is "
            f"{normalize_schedule_period(second.schedule_period)}. The merged "
            "qualification can only be one or the other, and its classes will be "
            "held to that window on top of the windows they already have."
        )
    if (first.delivery_mode or "regular") != (second.delivery_mode or "regular"):
        warnings.append(
            f"{first.name} is {first.delivery_mode or 'regular'} delivery and "
            f"{second.name} is {second.delivery_mode or 'regular'}. The merged "
            "qualification takes the mode you choose below."
        )
    if shared:
        warnings.append(
            f"{len(shared)} class(es) already belong to both, and are counted once."
        )

    return {
        "first": side(first, first_units),
        "second": side(second, second_units),
        "shared_class_count": len(shared),
        "combined_class_count": len(combined),
        "combined_classes": [
            {"id": uid, "name": names.get(uid, f"Class {uid}")}
            for uid in sorted(combined, key=lambda i: names.get(i, "").casefold())
        ],
        "suggested_name": suggested_merge_name(first.name, second.name),
        "suggested_num_groups": min(
            MAX_GROUPS, max(first.num_groups or 1, second.num_groups or 1)
        ),
        "warnings": warnings,
    }


def _validate_name(
    db: Session, *, timetable_session_id: int, name: str
) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise QualificationMergeError("The merged qualification needs a name.")
    if len(cleaned) > 200:
        raise QualificationMergeError("That name is too long (200 characters maximum).")
    taken = {
        q.name.strip().casefold()
        for q in db.query(Qualification)
        .filter(Qualification.timetable_session_id == timetable_session_id)
        .all()
    }
    if cleaned.casefold() in taken:
        # Including the sources themselves: they are still here afterwards, so
        # reusing one of their names would collide on (session, name).
        raise QualificationMergeError(f"A qualification named {cleaned!r} already exists.")
    return cleaned


def merge_qualifications(
    db: Session,
    *,
    timetable_session_id: int,
    first_qualification_id: int,
    second_qualification_id: int,
    name: str,
    num_groups: int,
    schedule_period: str | None = None,
    delivery_mode: str | None = None,
) -> dict:
    """Create a qualification holding both sources' classes, leaving both intact."""
    if first_qualification_id == second_qualification_id:
        raise QualificationMergeError("Pick two different qualifications to merge.")

    first = _load(
        db, timetable_session_id=timetable_session_id, qualification_id=first_qualification_id
    )
    second = _load(
        db, timetable_session_id=timetable_session_id, qualification_id=second_qualification_id
    )

    cleaned = _validate_name(db, timetable_session_id=timetable_session_id, name=name)

    groups = int(num_groups or 1)
    if groups < 1:
        raise QualificationMergeError("The merged qualification needs at least one group.")
    if groups > MAX_GROUPS:
        raise QualificationMergeError(f"A qualification can have at most {MAX_GROUPS} groups.")

    first_units = _linked_unit_ids(db, first.id)
    second_units = _linked_unit_ids(db, second.id)
    combined = first_units | second_units
    if not combined:
        raise QualificationMergeError(
            "Neither qualification has any classes, so there is nothing to merge."
        )

    period = normalize_schedule_period(
        schedule_period if schedule_period is not None else first.schedule_period
    )
    mode = delivery_mode or first.delivery_mode or "regular"

    merged = Qualification(
        timetable_session_id=timetable_session_id,
        name=cleaned,
        num_groups=groups,
        schedule_period=period,
        delivery_mode=mode,
        # Block settings only mean anything in block mode; taken from whichever
        # source the delivery mode came from so the two stay consistent.
        block_week_count=(
            first.block_week_count
            if mode == (first.delivery_mode or "regular")
            else second.block_week_count
        ),
        block_start_semester_week=(
            first.block_start_semester_week
            if mode == (first.delivery_mode or "regular")
            else second.block_start_semester_week
        ),
        # Never part of a stage family. A merge is not a stage of anything, and
        # inheriting a parent here would put it in a family whose other members
        # know nothing about it.
        parent_qualification_id=None,
    )
    db.add(merged)
    db.flush()

    # Additive: linking a class here leaves its existing links alone, which is
    # what keeps both sources whole.
    for unit_id in sorted(combined):
        db.add(UnitQualification(unit_id=unit_id, qualification_id=merged.id))

    _copy_online_student_counts(
        db, first=first, second=second, merged=merged
    )

    sync_qualification_regular_groups(db, merged, groups)
    replace_qualification_time_windows(db, merged)
    db.commit()

    shared = len(first_units & second_units)
    return {
        "qualification_id": merged.id,
        "name": merged.name,
        "class_count": len(combined),
        "shared_class_count": shared,
        "num_groups": merged.num_groups,
        "summary": (
            f"Merged {first.name} and {second.name} into {merged.name}: "
            f"{len(combined)} class(es)"
            + (f" ({shared} shared)" if shared else "")
            + f", {merged.num_groups} group(s). "
            f"{first.name} and {second.name} are unchanged."
        ),
    }


def _copy_online_student_counts(
    db: Session, *, first: Qualification, second: Qualification, merged: Qualification
) -> None:
    """Carry per-lecturer online cohort sizes onto the merged qualification.

    Copied rather than moved, since the sources keep theirs. Where a lecturer
    has a count against both, the two are added: the merged qualification
    covers both class lists, so it carries both cohorts.
    """
    totals: dict[int, int | None] = {}
    rows = (
        db.query(StaffQualificationOnlineStudents)
        .filter(
            StaffQualificationOnlineStudents.qualification_id.in_([first.id, second.id])
        )
        .all()
    )
    for row in rows:
        if row.student_count is None:
            totals.setdefault(row.staff_id, None)
            continue
        running = totals.get(row.staff_id)
        totals[row.staff_id] = row.student_count + (running or 0)

    for staff_id, count in totals.items():
        db.add(
            StaffQualificationOnlineStudents(
                staff_id=staff_id,
                qualification_id=merged.id,
                student_count=count,
            )
        )

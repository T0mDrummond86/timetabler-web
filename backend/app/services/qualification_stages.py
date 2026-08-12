"""Split one qualification into per-stage qualifications.

A stage is not a new concept in the data: most qualifications here are already
written as "… Stg1", "… Stg2", each its own record with its own groups. This
turns that convention into an operation — take a qualification holding every
class, and deal those classes out into a stage each.

Deliberately refuses to run once anything is timetabled. Re-linking classes
under a qualification whose groups already carry bookings would leave those
bookings pointing at a cohort that no longer teaches the class, and there is no
obviously right place to move them to — stages can have different group counts.
Better to say so than to guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from timetable.core.models import (
    Booking,
    Course,
    Qualification,
    Unit,
    UnitQualification,
)
from timetable.core.qualification_schedule import replace_qualification_time_windows

from .qualification_editor import sync_qualification_regular_groups


class StageSplitError(ValueError):
    """The split cannot be performed; the message is meant for the user."""


_STAGE_SUFFIX_RE = re.compile(r"\s*St(?:a?ge?)?\s*\d+\s*$", re.IGNORECASE)


def family_qualifications(
    db: Session, *, timetable_session_id: int, qualification_id: int
) -> list[Qualification]:
    """Every stage of the family this qualification belongs to, in stage order.

    A qualification that was never split is its own family of one, so callers
    can treat both cases the same.
    """
    qual = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == timetable_session_id,
        )
        .one_or_none()
    )
    if qual is None:
        raise LookupError("Qualification not found")

    if not qual.parent_qualification_id:
        return [qual]

    return (
        db.query(Qualification)
        .filter(
            Qualification.timetable_session_id == timetable_session_id,
            Qualification.parent_qualification_id == qual.parent_qualification_id,
        )
        # By id: the split keeps the original record as stage one and creates the
        # rest in order, so ids are the stage order and survive a rename.
        .order_by(Qualification.id)
        .all()
    )


def family_title(stages: list[Qualification]) -> str:
    """The whole qualification's name, with the stage suffix taken back off.

    Named after the root record — the one the split started from — so renaming
    a later stage does not rename the qualification it belongs to.
    """
    if not stages:
        return "Qualification"
    if len(stages) == 1:
        return stages[0].name
    root = next(
        (q for q in stages if q.parent_qualification_id == q.id),
        min(stages, key=lambda q: q.id),
    )
    stem = _STAGE_SUFFIX_RE.sub("", root.name).strip()
    return stem or root.name


@dataclass(frozen=True)
class StagePlan:
    name: str
    num_groups: int
    unit_ids: tuple[int, ...]


def _blocking_bookings(db: Session, qualification_id: int) -> int:
    course_ids = [
        c.id for c in db.query(Course).filter(Course.qualification_id == qualification_id).all()
    ]
    if not course_ids:
        return 0
    return db.query(Booking).filter(Booking.course_id.in_(course_ids)).count()


def _validate(
    db: Session,
    *,
    qual: Qualification,
    stages: list[StagePlan],
    timetable_session_id: int,
) -> None:
    if len(stages) < 2:
        raise StageSplitError("A split needs at least two stages.")

    names = [s.name.strip() for s in stages]
    if any(not n for n in names):
        raise StageSplitError("Every stage needs a name.")
    lowered = [n.casefold() for n in names]
    if len(set(lowered)) != len(lowered):
        raise StageSplitError("Stage names must differ from each other.")

    # A stage name that already belongs to a different qualification would
    # collide with the unique (session, name) constraint mid-write.
    clashes = (
        db.query(Qualification)
        .filter(
            Qualification.timetable_session_id == timetable_session_id,
            Qualification.id != qual.id,
        )
        .all()
    )
    taken = {q.name.strip().casefold() for q in clashes}
    for n in names:
        if n.casefold() in taken:
            raise StageSplitError(f"A qualification named {n!r} already exists.")

    linked_ids = {
        uq.unit_id
        for uq in db.query(UnitQualification)
        .filter(UnitQualification.qualification_id == qual.id)
        .all()
    }
    assigned: set[int] = set()
    for stage in stages:
        for uid in stage.unit_ids:
            if uid in assigned:
                raise StageSplitError("A class can only belong to one stage.")
            assigned.add(uid)
            if uid not in linked_ids:
                raise StageSplitError(
                    "Only classes already linked to this qualification can be assigned to a stage."
                )

    if any(s.num_groups < 1 for s in stages):
        raise StageSplitError("Each stage needs at least one group.")


def split_qualification_into_stages(
    db: Session,
    *,
    timetable_session_id: int,
    qualification_id: int,
    stages: list[StagePlan],
) -> dict:
    """Deal a qualification's classes into one qualification per stage.

    The original record becomes the first stage — keeping its settings and id —
    and the remaining stages are created alongside it. Classes not named in any
    stage stay on the first stage rather than being dropped.
    """
    qual = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == timetable_session_id,
        )
        .one_or_none()
    )
    if qual is None:
        raise LookupError("Qualification not found")

    booked = _blocking_bookings(db, qual.id)
    if booked:
        raise StageSplitError(
            f"{qual.name} has {booked} scheduled class(es) on its groups. "
            "Splitting now would leave them attached to a cohort that no longer "
            "teaches them. Unschedule those bookings first, then split."
        )

    _validate(db, qual=qual, stages=stages, timetable_session_id=timetable_session_id)

    assigned = {uid for s in stages for uid in s.unit_ids}
    all_linked = {
        uq.unit_id
        for uq in db.query(UnitQualification)
        .filter(UnitQualification.qualification_id == qual.id)
        .all()
    }
    # Anything left unassigned stays with stage one — losing a class silently
    # would be far worse than putting it somewhere obvious.
    leftovers = sorted(all_linked - assigned)

    created: list[Qualification] = []
    for index, stage in enumerate(stages):
        if index == 0:
            target = qual
            target.name = stage.name.strip()
            # Stage one points at itself, so every member of the family shares
            # one parent id and the family is a single equality test. A split
            # of an already-split stage keeps pointing at the original root.
            target.parent_qualification_id = qual.parent_qualification_id or qual.id
        else:
            target = Qualification(
                timetable_session_id=timetable_session_id,
                name=stage.name.strip(),
                num_groups=stage.num_groups,
                schedule_period=getattr(qual, "schedule_period", None) or "day",
                delivery_mode=getattr(qual, "delivery_mode", None) or "regular",
                block_week_count=getattr(qual, "block_week_count", None),
                block_start_semester_week=getattr(qual, "block_start_semester_week", None),
                parent_qualification_id=qual.parent_qualification_id or qual.id,
            )
            db.add(target)
            db.flush()
            created.append(target)

        # Group courses are named from the qualification, so the first stage's
        # existing courses carry the pre-split name. With no bookings to lose,
        # dropping and re-syncing is the clean way to get the codes right.
        for course in (
            db.query(Course).filter_by(qualification_id=target.id, is_block_cohort=0).all()
        ):
            db.delete(course)
        db.flush()
        sync_qualification_regular_groups(db, target, stage.num_groups)
        replace_qualification_time_windows(db, target)

    db.flush()

    # Re-link classes. Only links to this qualification are touched: a class may
    # sit under other qualifications too, and those are none of our business.
    stage_by_unit: dict[int, int] = {}
    for index, stage in enumerate(stages):
        target_id = qual.id if index == 0 else created[index - 1].id
        for uid in stage.unit_ids:
            stage_by_unit[uid] = target_id
    for uid in leftovers:
        stage_by_unit[uid] = qual.id

    for link in (
        db.query(UnitQualification)
        .filter(UnitQualification.qualification_id == qualification_id)
        .all()
    ):
        new_qual_id = stage_by_unit.get(link.unit_id)
        if new_qual_id is not None and new_qual_id != qualification_id:
            link.qualification_id = new_qual_id

    db.commit()

    result_ids = [qual.id] + [q.id for q in created]
    return {
        "stage_qualification_ids": result_ids,
        "unassigned_classes_kept_on_first_stage": len(leftovers),
        "summary": (
            f"Split into {len(stages)} stages: "
            + ", ".join(f"{s.name.strip()} ({len(s.unit_ids)} class(es))" for s in stages)
            + (f"; {len(leftovers)} unassigned class(es) stayed on the first stage" if leftovers else "")
        ),
    }


def stage_split_preview(db: Session, *, timetable_session_id: int, qualification_id: int) -> dict:
    """What the dialog needs: the classes to deal out, and whether it can run."""
    qual = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == timetable_session_id,
        )
        .one_or_none()
    )
    if qual is None:
        raise LookupError("Qualification not found")

    booked = _blocking_bookings(db, qual.id)
    classes = (
        db.query(Unit)
        .join(UnitQualification, UnitQualification.unit_id == Unit.id)
        .filter(UnitQualification.qualification_id == qual.id)
        .order_by(Unit.name)
        .all()
    )
    return {
        "qualification_id": qual.id,
        "name": qual.name,
        "num_groups": qual.num_groups or 1,
        "can_split": booked == 0 and len(classes) > 0,
        "blocked_reason": (
            f"{booked} class(es) are already scheduled on this qualification's groups. "
            "Unschedule them first, then split."
            if booked
            else ("This qualification has no classes to split." if not classes else "")
        ),
        "classes": [{"id": u.id, "name": u.name} for u in classes],
    }

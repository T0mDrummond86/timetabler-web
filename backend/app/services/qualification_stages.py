"""Split one qualification into per-stage qualifications, and re-split it later.

A stage is not a new concept in the data: most qualifications here are already
written as "… Stg1", "… Stg2", each its own record with its own groups. This
turns that convention into an operation — take a qualification holding every
class, and deal those classes out into a stage each.

Everything here works on the whole *family*, not on the one stage record the
user happens to have open. Splitting is not a one-shot decision: the first pass
at which class sits in which year is usually wrong, so opening the dialog on an
already-split qualification shows every class in it and lets the stages be
redealt, renamed, added to or dropped.

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
    QualificationTimeWindow,
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
    #: The existing stage this plan is for, when the family has already been
    #: split. Absent means "any stage record still going spare, else a new one",
    #: which is what a first split of an unsplit qualification sends.
    qualification_id: int | None = None


def _blocking_bookings(db: Session, qualification_ids: list[int]) -> int:
    """Bookings on any group of any stage in the family.

    The whole family is checked, not just the stage that was opened: a redeal
    moves classes between stages, so a booking anywhere in the family is one
    that could end up on a cohort that no longer teaches the class.
    """
    if not qualification_ids:
        return 0
    course_ids = [
        c.id
        for c in db.query(Course).filter(Course.qualification_id.in_(qualification_ids)).all()
    ]
    if not course_ids:
        return 0
    return db.query(Booking).filter(Booking.course_id.in_(course_ids)).count()


def _linked_unit_ids(db: Session, qualification_ids: list[int]) -> set[int]:
    if not qualification_ids:
        return set()
    return {
        uq.unit_id
        for uq in db.query(UnitQualification)
        .filter(UnitQualification.qualification_id.in_(qualification_ids))
        .all()
    }


def _validate(
    db: Session,
    *,
    family: list[Qualification],
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

    family_ids = [q.id for q in family]

    # A stage name that already belongs to a different qualification would
    # collide with the unique (session, name) constraint mid-write. Names
    # already held *inside* the family are fine — those records are being
    # renamed or dropped by this same operation.
    clashes = (
        db.query(Qualification)
        .filter(
            Qualification.timetable_session_id == timetable_session_id,
            Qualification.id.notin_(family_ids),
        )
        .all()
    )
    taken = {q.name.strip().casefold() for q in clashes}
    for n in names:
        if n.casefold() in taken:
            raise StageSplitError(f"A qualification named {n!r} already exists.")

    claimed: set[int] = set()
    for stage in stages:
        if stage.qualification_id is None:
            continue
        if stage.qualification_id not in family_ids:
            raise StageSplitError("A stage can only reuse a stage of this qualification.")
        if stage.qualification_id in claimed:
            raise StageSplitError("Two stages cannot be the same stage record.")
        claimed.add(stage.qualification_id)

    linked_ids = _linked_unit_ids(db, family_ids)
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


def _delete_stage(db: Session, qual: Qualification) -> None:
    """Remove a stage the redeal no longer has a use for.

    Only ever reached with the family's bookings already refused, and only for
    a record every class has been dealt away from, so there is nothing left on
    it worth keeping. Rows are removed explicitly rather than leaning on the
    database cascade, which SQLite only honours with foreign keys switched on.
    """
    db.query(UnitQualification).filter(UnitQualification.qualification_id == qual.id).delete(
        synchronize_session=False
    )
    db.query(QualificationTimeWindow).filter(
        QualificationTimeWindow.qualification_id == qual.id
    ).delete(synchronize_session=False)
    for course in db.query(Course).filter(Course.qualification_id == qual.id).all():
        db.delete(course)
    db.flush()
    db.delete(qual)
    db.flush()


def split_qualification_into_stages(
    db: Session,
    *,
    timetable_session_id: int,
    qualification_id: int,
    stages: list[StagePlan],
) -> dict:
    """Deal a qualification's classes into one qualification per stage.

    Works on the whole family the given qualification belongs to. A first split
    has a family of one, so the original record becomes the first stage — its
    id and settings survive — and the rest are created alongside it. A redeal
    of an already-split family reuses the stage records the plans name, creates
    any extra stages asked for, and drops the ones no plan wants (safe: every
    class has been dealt away from them by then).

    Classes not named in any stage stay on the first stage rather than being
    dropped.
    """
    family = family_qualifications(
        db, timetable_session_id=timetable_session_id, qualification_id=qualification_id
    )
    family_ids = [q.id for q in family]
    was_split = len(family) > 1
    title = family_title(family)

    booked = _blocking_bookings(db, family_ids)
    if booked:
        raise StageSplitError(
            f"{title} has {booked} scheduled class(es) on its groups. "
            "Splitting now would leave them attached to a cohort that no longer "
            "teaches them. Unschedule those bookings first, then split."
        )

    _validate(db, family=family, stages=stages, timetable_session_id=timetable_session_id)

    assigned = {uid for s in stages for uid in s.unit_ids}
    all_linked = _linked_unit_ids(db, family_ids)
    # Anything left unassigned stays with stage one — losing a class silently
    # would be far worse than putting it somewhere obvious.
    leftovers = sorted(all_linked - assigned)

    # Match each plan to a stage record. A plan naming one takes it; a plan
    # naming none takes the next record still going spare, which is how a first
    # split keeps the original qualification as its stage one. Records nothing
    # claims are dropped once their classes have moved off them.
    by_id = {q.id: q for q in family}
    claimed = {s.qualification_id for s in stages if s.qualification_id is not None}
    spare = [q for q in family if q.id not in claimed]
    reused: list[Qualification | None] = []
    for stage in stages:
        if stage.qualification_id is not None:
            reused.append(by_id[stage.qualification_id])
        elif spare:
            reused.append(spare.pop(0))
        else:
            reused.append(None)
    dropped = spare
    dropped_names = [q.name for q in dropped]

    # Stages can be renamed into each other's names ("Stg1" and "Stg2" swapping
    # what they hold). Park every existing name first so no intermediate write
    # trips the unique (session, name) constraint.
    for q in family:
        q.name = f"__stage_split_{q.id}__"
    db.flush()

    # Dropped stages go now, before the kept ones are renamed and re-grouped:
    # their group courses are named after them, and a kept stage taking a
    # dropped one's name wants those course codes free. Nothing is lost — where
    # each class ends up was worked out above, and is written below.
    for stage_record in dropped:
        _delete_stage(db, stage_record)

    original_root_id = family[0].parent_qualification_id or family[0].id
    retained_ids = {q.id for q in reused if q is not None}
    # If the record the family is keyed on is being dropped, the family needs a
    # new key, otherwise every stage would point at a row that no longer exists.
    root_id = original_root_id if original_root_id in retained_ids else None

    targets: list[Qualification] = []
    for existing, stage in zip(reused, stages):
        if existing is not None:
            existing.name = stage.name.strip()
            targets.append(existing)
            continue
        template = family[0]
        created = Qualification(
            timetable_session_id=timetable_session_id,
            name=stage.name.strip(),
            num_groups=stage.num_groups,
            schedule_period=getattr(template, "schedule_period", None) or "day",
            delivery_mode=getattr(template, "delivery_mode", None) or "regular",
            block_week_count=getattr(template, "block_week_count", None),
            block_start_semester_week=getattr(template, "block_start_semester_week", None),
        )
        db.add(created)
        db.flush()
        targets.append(created)

    if root_id is None:
        root_id = targets[0].id
    # Every stage shares one parent id and stage one points at itself, so the
    # family is a single equality test. A redeal of an already-split family
    # keeps pointing at the original root.
    for target in targets:
        target.parent_qualification_id = root_id
    db.flush()

    for target, stage in zip(targets, stages):
        # Group courses are named from the qualification, so a stage that kept
        # its record still carries the pre-rename codes. With no bookings to
        # lose, dropping and re-syncing is the clean way to get them right.
        for course in (
            db.query(Course).filter_by(qualification_id=target.id, is_block_cohort=0).all()
        ):
            db.delete(course)
        db.flush()
        sync_qualification_regular_groups(db, target, stage.num_groups)
        replace_qualification_time_windows(db, target)

    db.flush()

    # Re-link classes. Only links within this family are touched: a class may
    # sit under other qualifications too, and those are none of our business.
    # Cleared and rewritten rather than repointed, because a class linked to two
    # stages of the same family would otherwise collide on the composite key.
    stage_by_unit: dict[int, int] = {}
    for target, stage in zip(targets, stages):
        for uid in stage.unit_ids:
            stage_by_unit[uid] = target.id
    for uid in leftovers:
        stage_by_unit[uid] = targets[0].id

    if stage_by_unit:
        db.query(UnitQualification).filter(
            UnitQualification.qualification_id.in_(family_ids),
            UnitQualification.unit_id.in_(list(stage_by_unit)),
        ).delete(synchronize_session=False)
        db.flush()
        for uid, target_id in sorted(stage_by_unit.items()):
            db.add(UnitQualification(unit_id=uid, qualification_id=target_id))
        db.flush()

    db.commit()

    verb = "Redealt into" if was_split else "Split into"
    return {
        "stage_qualification_ids": [t.id for t in targets],
        "unassigned_classes_kept_on_first_stage": len(leftovers),
        "summary": (
            f"{verb} {len(stages)} stages: "
            + ", ".join(f"{s.name.strip()} ({len(s.unit_ids)} class(es))" for s in stages)
            + (f"; {len(leftovers)} unassigned class(es) stayed on the first stage" if leftovers else "")
            + (f"; removed {len(dropped_names)} empty stage(s)" if dropped_names else "")
        ),
    }


def stage_split_preview(db: Session, *, timetable_session_id: int, qualification_id: int) -> dict:
    """What the dialog needs: every class in the qualification, and where it sits.

    Deliberately spans the whole family rather than the one stage that happens
    to be open. Re-dealing a split only makes sense with all of the classes on
    the table — a class in the wrong year is invisible from the stage it should
    have been in.
    """
    family = family_qualifications(
        db, timetable_session_id=timetable_session_id, qualification_id=qualification_id
    )
    family_ids = [q.id for q in family]
    is_split = len(family) > 1

    booked = _blocking_bookings(db, family_ids)
    rows = (
        db.query(Unit, UnitQualification.qualification_id)
        .join(UnitQualification, UnitQualification.unit_id == Unit.id)
        .filter(UnitQualification.qualification_id.in_(family_ids))
        .order_by(Unit.name)
        .all()
    )
    classes: list[dict] = []
    seen: set[int] = set()
    for unit, stage_id in rows:
        if unit.id in seen:
            continue
        seen.add(unit.id)
        classes.append(
            {"id": unit.id, "name": unit.name, "stage_qualification_id": int(stage_id)}
        )

    return {
        "qualification_id": qualification_id,
        "name": family_title(family),
        "num_groups": family[0].num_groups or 1,
        "is_split": is_split,
        "stages": [
            {"id": q.id, "name": q.name, "num_groups": q.num_groups or 1} for q in family
        ],
        "can_split": booked == 0 and len(classes) > 0,
        "blocked_reason": (
            f"{booked} class(es) are already scheduled on this qualification's groups. "
            "Unschedule them first, then split."
            if booked
            else ("This qualification has no classes to split." if not classes else "")
        ),
        "classes": classes,
    }

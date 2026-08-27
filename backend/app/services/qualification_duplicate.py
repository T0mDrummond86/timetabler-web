"""Copy a qualification without copying its classes.

The same qualification often runs twice over — a second intake, a night
version, the same programme at another campus. Making the second one by hand
means retyping every class, and the retyped classes are *new records*, so the
timetable then has two "ICTNWK540" that have to be folded back together in the
Classes tab (see ``class_consolidation``). This exists to stop that happening
in the first place.

So the copy shares its classes rather than owning its own: a class may belong
to any number of qualifications at once (``UnitQualification``), and the
duplicate simply links the same rows. Edit the class's length or unit codes
afterwards and both qualifications see the change, which is the point — they
are the same class.

**A whole qualification is copied, not one stage of it.** A stage is its own
Qualification record — "… Stg1", "… Stg2" — so duplicating only the record that
happens to be open produces a lone stage of a qualification that does not
exist. The copy takes every stage, keeps the stage structure, and hangs it off
a new root of its own.

Which records count as stages of one qualification is answered two ways,
because real sessions contain both. A qualification split inside the app leaves
its stages sharing a parent id, which is exact. A qualification imported from a
course study plan does not: its stages arrive as unrelated records that are
only recognisable as a family by their names — identical apart from a trailing
"Stg1"/"Stage 2". Both are used, and the dialog lists the stages it found
before anything is created, since a name rule is a guess and the user is the
one who can see whether it guessed right.

What each stage of the copy gets of its own is groups. Cohorts are
per-qualification by definition, so every stage gets a fresh set, named after
its own name, with the same classes sitting in each group's holding area ready
to place.

Bookings are not copied. A duplicate starts with an empty timetable: its groups
are new, nobody has agreed to teach them yet, and copying placecards would put
lecturers and rooms into a second booking they never agreed to.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from timetable.core.models import (
    Course,
    CourseUnit,
    Qualification,
    StaffQualificationOnlineStudents,
    UnitQualification,
)
from timetable.core.qualification_schedule import (
    normalize_schedule_period,
    replace_qualification_time_windows,
)

from .qualification_editor import sync_qualification_regular_groups
from .qualification_stages import _STAGE_SUFFIX_RE, family_qualifications

MAX_NAME_LENGTH = 200

#: The number inside a trailing stage suffix, for ordering a family that was
#: never split and so has no creation order to go by.
_STAGE_NUMBER_RE = re.compile(r"St(?:a?ge?)?\s*(\d+)\s*$", re.IGNORECASE)


class QualificationDuplicateError(ValueError):
    """The duplicate cannot be made; the message is meant for the user."""


def _taken_names(db: Session, *, timetable_session_id: int) -> set[str]:
    return {
        q.name.strip().casefold()
        for q in db.query(Qualification)
        .filter(Qualification.timetable_session_id == timetable_session_id)
        .all()
    }


def _free_name(base: str, taken: set[str]) -> str:
    """``base``, or ``base (2)`` and so on until one is free.

    ``taken`` is updated, so a caller naming several stages in a row cannot
    hand the same name to two of them.
    """
    candidate = base.strip() or "Qualification"
    n = 1
    while candidate.casefold() in taken or len(candidate) > MAX_NAME_LENGTH:
        n += 1
        suffix = f" ({n})"
        candidate = f"{base.strip()[: MAX_NAME_LENGTH - len(suffix)]}{suffix}"
        if n > 200:  # pathological; stop rather than spin
            raise QualificationDuplicateError(
                "Could not find a free name — give the duplicate a name of your own."
            )
    taken.add(candidate.casefold())
    return candidate


def suggested_duplicate_name(db: Session, *, timetable_session_id: int, name: str) -> str:
    """``X (copy)``, then ``X (copy 2)`` and so on until one is free.

    Offered as the default in the dialog, not imposed: the useful name is
    usually something like "Cert IV Cyber Security 2027 intake", which only the
    person making it knows.
    """
    taken = _taken_names(db, timetable_session_id=timetable_session_id)
    base = name.strip() or "Qualification"
    candidate = f"{base} (copy)"
    n = 2
    while candidate.casefold() in taken or len(candidate) > MAX_NAME_LENGTH:
        if len(candidate) > MAX_NAME_LENGTH:
            # Nothing sensible left to suggest; the dialog requires a name
            # anyway, so hand back something short and obviously placeholder.
            return f"Copy {n}"
        candidate = f"{base} (copy {n})"
        n += 1
    return candidate


def _stage_copy_name(stage_name: str, stem: str, new_stem: str) -> str:
    """A stage's name under the copy's title.

    "Cert IV Cyber Stg2" under a new title of "Cert IV Cyber 2027" becomes
    "Cert IV Cyber 2027 Stg2" — the stem swapped, the stage marker left alone,
    whatever form it takes. A stage renamed to something that no longer starts
    with the family stem has no stem to swap, so it is qualified instead.
    """
    if stem and stage_name.casefold().startswith(stem.casefold()):
        return f"{new_stem}{stage_name[len(stem):]}".strip()
    return f"{new_stem} — {stage_name}".strip()


def _stem(name: str) -> str:
    """"Dip of IT Stg2" -> "Dip of IT". The app's own stage-suffix rule."""
    return _STAGE_SUFFIX_RE.sub("", name or "").strip()


def _stage_number(name: str) -> int:
    match = _STAGE_NUMBER_RE.search(name or "")
    # Anything without a number sorts last, keeping a non-conforming member
    # from displacing the real stage one.
    return int(match.group(1)) if match else 10_000


def _family(
    db: Session, *, timetable_session_id: int, qualification_id: int
) -> tuple[list[Qualification], str]:
    """Every stage of the qualification the given record belongs to, and its name.

    Two rules, unioned, because sessions contain both kinds of family:

    * a shared parent id, left by a split done inside the app -- exact;
    * a name identical apart from a trailing stage suffix, which is how an
      imported qualification's stages arrive, related only by what they are
      called.

    The name rule is deliberately narrow. "Cert4 Cyber STG1 -GRP1" does not end
    in a stage suffix, so it strips to itself and groups with nothing; only
    names that differ by the suffix alone are pulled in.
    """
    split_family = family_qualifications(
        db, timetable_session_id=timetable_session_id, qualification_id=qualification_id
    )
    if not split_family:
        raise LookupError(f"Qualification {qualification_id} not found")

    selected = next(
        (q for q in split_family if q.id == qualification_id), split_family[0]
    )
    stem = _stem(selected.name) or selected.name

    by_id = {q.id: q for q in split_family}
    for q in (
        db.query(Qualification)
        .filter(Qualification.timetable_session_id == timetable_session_id)
        .all()
    ):
        if q.id not in by_id and _stem(q.name).casefold() == stem.casefold():
            by_id[q.id] = q

    stages = sorted(by_id.values(), key=lambda q: (_stage_number(q.name), q.id))
    if len(stages) == 1:
        # A qualification on its own keeps its own name: stripping a suffix off
        # an unsplit "Cert IV Stage 2" would rename something that is not a
        # stage of anything.
        return stages, stages[0].name
    return stages, stem


def _linked_unit_ids(db: Session, qualification_ids: list[int]) -> set[int]:
    return {
        uq.unit_id
        for uq in db.query(UnitQualification)
        .filter(UnitQualification.qualification_id.in_(qualification_ids))
        .all()
    }


def duplicate_preview(
    db: Session, *, timetable_session_id: int, qualification_id: int
) -> dict:
    """What the duplicate would contain, and the name to offer for it."""
    stages, title = _family(
        db, timetable_session_id=timetable_session_id, qualification_id=qualification_id
    )
    ids = [q.id for q in stages]
    return {
        # The root of the family, not whichever stage was open.
        "source_id": stages[0].id,
        "source_name": title,
        "stage_count": len(stages),
        "stage_names": [q.name for q in stages],
        # Distinct across the family: a class linked to two stages is one class.
        "class_count": len(_linked_unit_ids(db, ids)),
        "num_groups": sum(max(1, q.num_groups or 1) for q in stages),
        "suggested_name": suggested_duplicate_name(
            db, timetable_session_id=timetable_session_id, name=title
        ),
    }


def duplicate_qualification(
    db: Session,
    *,
    timetable_session_id: int,
    qualification_id: int,
    name: str | None = None,
) -> dict:
    """Copy a whole qualification — every stage of it — sharing its classes."""
    stages, stem = _family(
        db, timetable_session_id=timetable_session_id, qualification_id=qualification_id
    )

    requested = (name if name is not None else suggested_duplicate_name(
        db, timetable_session_id=timetable_session_id, name=stem
    )).strip()
    if not requested:
        raise QualificationDuplicateError("The duplicate needs a name.")
    if len(requested) > MAX_NAME_LENGTH:
        raise QualificationDuplicateError(
            f"That name is too long ({MAX_NAME_LENGTH} characters maximum)."
        )

    taken = _taken_names(db, timetable_session_id=timetable_session_id)
    if len(stages) == 1 and requested.casefold() in taken:
        # A single qualification is named directly, so a collision is the user's
        # to fix rather than something to quietly work around.
        raise QualificationDuplicateError(f"A qualification named {requested!r} already exists.")

    copies: list[Qualification] = []
    root_id: int | None = None
    total_units = 0
    total_assigned = 0

    for index, source in enumerate(stages):
        stage_name = (
            requested
            if len(stages) == 1
            else _stage_copy_name(source.name, stem, requested)
        )
        groups = max(1, int(source.num_groups or 1))
        copy = Qualification(
            timetable_session_id=timetable_session_id,
            name=_free_name(stage_name, taken),
            num_groups=groups,
            schedule_period=normalize_schedule_period(source.schedule_period),
            delivery_mode=source.delivery_mode or "regular",
            block_week_count=source.block_week_count,
            block_start_semester_week=source.block_start_semester_week,
            # Filled in below: the copy is its own family, never joined to the
            # one it came from, whose other stages know nothing about it.
            parent_qualification_id=None,
        )
        db.add(copy)
        db.flush()

        if len(stages) > 1:
            # Stage one points at itself, matching how a split builds a family,
            # so every member shares one parent id.
            if index == 0:
                root_id = copy.id
            copy.parent_qualification_id = root_id

        # The same class rows, linked again. Additive, so the source keeps its
        # own links and nothing about it changes.
        unit_ids = sorted(_linked_unit_ids(db, [source.id]))
        for unit_id in unit_ids:
            db.add(UnitQualification(unit_id=unit_id, qualification_id=copy.id))
        total_units += len(unit_ids)

        sync_qualification_regular_groups(db, copy, groups)
        replace_qualification_time_windows(db, copy)
        db.flush()

        total_assigned += _copy_group_holdings(db, source=source, copy=copy)
        _copy_online_student_counts(db, source=source, copy=copy)
        copies.append(copy)

    db.commit()

    stage_note = (
        f", across {len(copies)} stages" if len(copies) > 1 else ""
    )
    return {
        # The stage the caller should open: the root of the new family.
        "qualification_id": copies[0].id,
        "name": copies[0].name if len(copies) == 1 else requested,
        "source_name": stem,
        "stage_count": len(copies),
        "stage_names": [q.name for q in copies],
        "class_count": len(_linked_unit_ids(db, [q.id for q in copies])),
        "num_groups": sum(q.num_groups or 1 for q in copies),
        "groups_assigned": total_assigned,
        "summary": (
            f"Duplicated {stem} as {requested}: "
            f"{len(_linked_unit_ids(db, [q.id for q in copies]))} class(es) shared "
            f"(not copied), {sum(q.num_groups or 1 for q in copies)} new group(s)"
            f"{stage_note}. The timetable for the new groups starts empty."
        ),
    }


def _regular_groups(db: Session, qualification_id: int) -> list[Course]:
    return (
        db.query(Course)
        .filter(Course.qualification_id == qualification_id, Course.is_block_cohort == 0)
        .order_by(Course.code)
        .all()
    )


def _copy_group_holdings(db: Session, *, source: Qualification, copy: Qualification) -> int:
    """Give each new group the classes its opposite number holds.

    Matched by position, since the copy has the same number of groups and the
    codes only differ by the qualification name. Without this the new groups
    would be empty and every class would have to be added to each of them by
    hand -- the retyping this whole feature exists to avoid.
    """
    src_groups = _regular_groups(db, source.id)
    new_groups = _regular_groups(db, copy.id)
    if not src_groups or not new_groups:
        return 0

    holdings: dict[int, list[int]] = {c.id: [] for c in src_groups}
    for cu in (
        db.query(CourseUnit)
        .filter(CourseUnit.course_id.in_([c.id for c in src_groups]))
        .all()
    ):
        holdings.setdefault(cu.course_id, []).append(cu.unit_id)

    added = 0
    for index, new_course in enumerate(new_groups):
        # More new groups than old is only possible if the source's num_groups
        # disagrees with its actual courses; fall back to the last one rather
        # than leaving the extras empty.
        src = src_groups[min(index, len(src_groups) - 1)]
        for unit_id in holdings.get(src.id, []):
            db.add(CourseUnit(course_id=new_course.id, unit_id=unit_id))
            added += 1
    return added


def _copy_online_student_counts(
    db: Session, *, source: Qualification, copy: Qualification
) -> None:
    """Carry per-lecturer online cohort sizes onto the copy.

    Copied, not moved: the source keeps its own. They are an attribute of the
    qualification's delivery, so a duplicate of that delivery starts with the
    same expectation, which is easier to correct than to reconstruct.
    """
    rows = (
        db.query(StaffQualificationOnlineStudents)
        .filter(StaffQualificationOnlineStudents.qualification_id == source.id)
        .all()
    )
    for row in rows:
        db.add(
            StaffQualificationOnlineStudents(
                staff_id=row.staff_id,
                qualification_id=copy.id,
                student_count=row.student_count,
            )
        )

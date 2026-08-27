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

What the copy does get of its own is groups. Cohorts are per-qualification by
definition, so the duplicate gets a fresh set, named after its own name, with
the same classes sitting in each group's holding area ready to place.

Bookings are not copied. A duplicate starts with an empty timetable: its groups
are new, nobody has agreed to teach them yet, and copying placecards would put
lecturers and rooms into a second booking they never agreed to.
"""
from __future__ import annotations

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

MAX_NAME_LENGTH = 200


class QualificationDuplicateError(ValueError):
    """The duplicate cannot be made; the message is meant for the user."""


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


def _taken_names(db: Session, *, timetable_session_id: int) -> set[str]:
    return {
        q.name.strip().casefold()
        for q in db.query(Qualification)
        .filter(Qualification.timetable_session_id == timetable_session_id)
        .all()
    }


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


def _validate_name(db: Session, *, timetable_session_id: int, name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise QualificationDuplicateError("The duplicate needs a name.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise QualificationDuplicateError(
            f"That name is too long ({MAX_NAME_LENGTH} characters maximum)."
        )
    if cleaned.casefold() in _taken_names(db, timetable_session_id=timetable_session_id):
        # The source is still here, so its own name would collide too.
        raise QualificationDuplicateError(f"A qualification named {cleaned!r} already exists.")
    return cleaned


def duplicate_preview(
    db: Session, *, timetable_session_id: int, qualification_id: int
) -> dict:
    """What the duplicate would contain, and the name to offer for it."""
    source = _load(
        db, timetable_session_id=timetable_session_id, qualification_id=qualification_id
    )
    class_count = (
        db.query(UnitQualification)
        .filter(UnitQualification.qualification_id == source.id)
        .count()
    )
    return {
        "source_id": source.id,
        "source_name": source.name,
        "class_count": class_count,
        "num_groups": source.num_groups or 1,
        "suggested_name": suggested_duplicate_name(
            db, timetable_session_id=timetable_session_id, name=source.name
        ),
    }


def duplicate_qualification(
    db: Session,
    *,
    timetable_session_id: int,
    qualification_id: int,
    name: str | None = None,
) -> dict:
    """Copy a qualification, sharing its classes rather than recreating them."""
    source = _load(
        db, timetable_session_id=timetable_session_id, qualification_id=qualification_id
    )

    cleaned = _validate_name(
        db,
        timetable_session_id=timetable_session_id,
        name=name
        if name is not None
        else suggested_duplicate_name(
            db, timetable_session_id=timetable_session_id, name=source.name
        ),
    )

    groups = max(1, int(source.num_groups or 1))
    copy = Qualification(
        timetable_session_id=timetable_session_id,
        name=cleaned,
        num_groups=groups,
        schedule_period=normalize_schedule_period(source.schedule_period),
        delivery_mode=source.delivery_mode or "regular",
        block_week_count=source.block_week_count,
        block_start_semester_week=source.block_start_semester_week,
        # Not a stage of anything. Inheriting the source's parent would drop the
        # copy into a stage family whose other members know nothing about it,
        # and the Qualifications list would show it as one of their stages.
        parent_qualification_id=None,
    )
    db.add(copy)
    db.flush()

    # The same class rows, linked again. Additive, so the source keeps its own
    # links and nothing about it changes.
    unit_ids = sorted(
        uq.unit_id
        for uq in db.query(UnitQualification)
        .filter(UnitQualification.qualification_id == source.id)
        .all()
    )
    for unit_id in unit_ids:
        db.add(UnitQualification(unit_id=unit_id, qualification_id=copy.id))

    sync_qualification_regular_groups(db, copy, groups)
    replace_qualification_time_windows(db, copy)
    db.flush()

    assigned = _copy_group_holdings(db, source=source, copy=copy)
    _copy_online_student_counts(db, source=source, copy=copy)

    db.commit()

    return {
        "qualification_id": copy.id,
        "name": copy.name,
        "source_name": source.name,
        "class_count": len(unit_ids),
        "num_groups": copy.num_groups,
        "groups_assigned": assigned,
        "summary": (
            f"Duplicated {source.name} as {copy.name}: {len(unit_ids)} class(es) shared "
            f"(not copied), {copy.num_groups} new group(s). "
            f"The timetable for the new groups starts empty."
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

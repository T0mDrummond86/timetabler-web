"""Collapse duplicate classes into one, linked to every qualification they served.

The same class is often delivered under several qualifications but arrives as
separate Class records, because each course study plan is imported on its own.
Class names are unique within a session, so the duplicates cannot look
identical -- they come in as "ICTNWK540 CertIV" and "ICTNWK540 Dip". Shared
unit codes are the giveaway, but only a hint: two classes can legitimately
teach the same code. So a person marks them, and this consolidates them.

Deliberately *not* called a merge in the UI. "Merge classes" already means
joining two clashing bookings in the staff view, and the two do entirely
different things to entirely different rows.

What survives is the class you keep, unchanged. What moves is the things that
would otherwise be destroyed with the absorbed rows: the qualification links
(the point of the exercise), the cohorts that deliver it, its placecards, and
any lecturer preference pointing at it. Everything else on the absorbed classes
-- allowed rooms, competencies, online counts, LAPs, unit codes -- goes with
them, which is why the caller has to be told.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from timetable.core.models import (
    Booking,
    Course,
    CourseUnit,
    Qualification,
    StaffCompetency,
    StaffPreference,
    Unit,
    UnitAllowedRoom,
    UnitQualification,
)


class ClassConsolidationError(ValueError):
    """The consolidation cannot be performed; the message is for the user."""


#: A national training unit code: letters then digits, sometimes a trailing
#: letter -- ICTNWK540, BSBXTW401, VU23213, MEM30031. The field is free text and
#: real sessions have plenty that is not a code in it ("LAB", "Robotics",
#: "SfS", a lecturer's surname). Matching on those produced nonsense
#: suggestions -- every class with "LAB" in the field looked like a duplicate of
#: every other -- so anything that is not code-shaped is ignored.
_UNIT_CODE = re.compile(r"^[A-Za-z]{2,6}\d{3,5}[A-Za-z]?$")


def _codes(unit: Unit) -> set[str]:
    """Unit codes on a class, normalised. Free text, comma separated."""
    raw = getattr(unit, "component_codes", None) or ""
    return {
        part.strip().casefold()
        for part in raw.split(",")
        if part.strip() and _UNIT_CODE.match(part.strip())
    }


def suggested_common_class_ids(db: Session, *, timetable_session_id: int) -> set[int]:
    """Classes sharing a unit code with a different class in the same session.

    A hint for the person doing the marking, computed rather than stored: the
    answer changes whenever a code is edited, and a stored copy would go stale
    without anything saying so.
    """
    units = (
        db.query(Unit).filter(Unit.timetable_session_id == timetable_session_id).all()
    )
    by_code: dict[str, list[int]] = {}
    for u in units:
        for code in _codes(u):
            by_code.setdefault(code, []).append(u.id)

    out: set[int] = set()
    for ids in by_code.values():
        if len(ids) > 1:
            out.update(ids)
    return out


def _load(db: Session, *, timetable_session_id: int, unit_ids: list[int]) -> list[Unit]:
    rows = (
        db.query(Unit)
        .filter(
            Unit.id.in_(unit_ids),
            Unit.timetable_session_id == timetable_session_id,
        )
        .all()
    )
    found = {u.id for u in rows}
    missing = [i for i in unit_ids if i not in found]
    if missing:
        # Also the cross-session case: a class from another session is simply
        # not found here, which is the right answer rather than a leak.
        raise LookupError(f"Class not found in this session: {missing}")
    return rows


def consolidation_preview(
    db: Session,
    *,
    timetable_session_id: int,
    survivor_id: int,
    absorbed_ids: list[int],
) -> dict:
    """What folding these classes would do, before it is done.

    Consolidation deletes rows, so the dialog has to be able to say what is
    about to be lost as well as what is about to be gained. The counts here are
    the same ones the result reports, worked out without writing anything.
    """
    absorbed_ids = [i for i in dict.fromkeys(absorbed_ids) if i != survivor_id]
    if not absorbed_ids:
        raise ClassConsolidationError(
            "Pick at least two classes: one to keep and one to fold into it."
        )

    units = _load(
        db,
        timetable_session_id=timetable_session_id,
        unit_ids=[survivor_id, *absorbed_ids],
    )
    by_id = {u.id: u for u in units}
    survivor = by_id[survivor_id]

    qual_names = dict(
        db.query(Qualification.id, Qualification.name)
        .filter(Qualification.timetable_session_id == timetable_session_id)
        .all()
    )
    course_codes = dict(
        db.query(Course.id, Course.code)
        .filter(Course.timetable_session_id == timetable_session_id)
        .all()
    )

    all_ids = [survivor_id, *absorbed_ids]
    quals_by_unit: dict[int, list[int]] = {i: [] for i in all_ids}
    for uq in (
        db.query(UnitQualification).filter(UnitQualification.unit_id.in_(all_ids)).all()
    ):
        quals_by_unit[uq.unit_id].append(uq.qualification_id)

    courses_by_unit: dict[int, list[int]] = {i: [] for i in all_ids}
    for cu in db.query(CourseUnit).filter(CourseUnit.unit_id.in_(all_ids)).all():
        courses_by_unit[cu.unit_id].append(cu.course_id)

    bookings_by_unit: dict[int, int] = {i: 0 for i in all_ids}
    for b in db.query(Booking).filter(Booking.unit_id.in_(all_ids)).all():
        bookings_by_unit[b.unit_id] = bookings_by_unit.get(b.unit_id, 0) + 1

    def side(unit: Unit) -> dict:
        return {
            "id": unit.id,
            "name": unit.name,
            "component_codes": unit.component_codes,
            "length_slots": unit.length_slots,
            "qualifications": sorted(
                qual_names.get(q, f"#{q}") for q in quals_by_unit.get(unit.id, [])
            ),
            "groups": sorted(
                course_codes.get(c, f"#{c}") for c in courses_by_unit.get(unit.id, [])
            ),
            "booking_count": bookings_by_unit.get(unit.id, 0),
        }

    combined_quals = {q for i in all_ids for q in quals_by_unit.get(i, [])}
    combined_groups = {c for i in all_ids for c in courses_by_unit.get(i, [])}

    # --- what will not survive ------------------------------------------------
    warnings: list[str] = []
    lost_rooms = (
        db.query(UnitAllowedRoom).filter(UnitAllowedRoom.unit_id.in_(absorbed_ids)).count()
    )
    if lost_rooms:
        warnings.append(
            f"{lost_rooms} room restriction(s) on the folded classes will be discarded — "
            f"{survivor.name} keeps its own."
        )
    lost_comps = (
        db.query(StaffCompetency).filter(StaffCompetency.unit_id.in_(absorbed_ids)).count()
    )
    if lost_comps:
        warnings.append(
            f"{lost_comps} lecturer competency link(s) on the folded classes will be "
            f"discarded — {survivor.name} keeps its own."
        )

    absorbed_codes = sorted(
        {c for i in absorbed_ids for c in _codes(by_id[i])} - _codes(survivor)
    )
    if absorbed_codes:
        warnings.append(
            "These unit codes are only on the classes being folded in: "
            + ", ".join(c.upper() for c in absorbed_codes)
            + ". They are lost unless you carry them across."
        )

    lengths = {by_id[i].length_slots for i in all_ids if by_id[i].length_slots}
    if len(lengths) > 1:
        warnings.append(
            f"The classes are different lengths; {survivor.name}'s length is kept and "
            "existing placecards are not resized."
        )

    return {
        "survivor": side(survivor),
        "absorbed": [side(by_id[i]) for i in absorbed_ids],
        "qualifications_gained": len(combined_quals) - len(set(quals_by_unit[survivor_id])),
        "groups_gained": len(combined_groups) - len(set(courses_by_unit[survivor_id])),
        "bookings_moving": sum(bookings_by_unit.get(i, 0) for i in absorbed_ids),
        "combined_qualifications": sorted(
            qual_names.get(q, f"#{q}") for q in combined_quals
        ),
        "warnings": warnings,
    }


def consolidate_classes(
    db: Session,
    *,
    timetable_session_id: int,
    survivor_id: int,
    absorbed_ids: list[int],
    merge_codes: bool = False,
) -> dict:
    """Fold ``absorbed_ids`` into ``survivor_id``.

    ``merge_codes`` appends unit codes that only the folded classes carried.
    Off here because the service's promise is that the survivor is left as it
    is; the dialog offers it ticked, because a surviving class that no longer
    records the units it delivers is a quiet data loss that shows up later in
    the admin export.
    """
    absorbed_ids = [i for i in dict.fromkeys(absorbed_ids) if i != survivor_id]
    if not absorbed_ids:
        raise ClassConsolidationError(
            "Pick at least two classes: one to keep and one to fold into it."
        )

    units = _load(
        db,
        timetable_session_id=timetable_session_id,
        unit_ids=[survivor_id, *absorbed_ids],
    )
    by_id = {u.id: u for u in units}
    survivor = by_id[survivor_id]

    # --- qualification links: the whole point ---------------------------------
    # Composite primary key, so a link the survivor already has must not be
    # inserted again.
    have = {
        uq.qualification_id
        for uq in db.query(UnitQualification)
        .filter(UnitQualification.unit_id == survivor_id)
        .all()
    }
    gained_quals = 0
    for uq in (
        db.query(UnitQualification)
        .filter(UnitQualification.unit_id.in_(absorbed_ids))
        .all()
    ):
        if uq.qualification_id not in have:
            db.add(
                UnitQualification(
                    unit_id=survivor_id, qualification_id=uq.qualification_id
                )
            )
            have.add(uq.qualification_id)
            gained_quals += 1

    # --- cohorts that deliver it ---------------------------------------------
    # course_unit cascades away with the absorbed rows. Without carrying it
    # across, a cohort that took the absorbed class would lose it from its
    # holding area even though its placecards were repointed.
    have_courses = {
        cu.course_id
        for cu in db.query(CourseUnit).filter(CourseUnit.unit_id == survivor_id).all()
    }
    gained_courses = 0
    for cu in db.query(CourseUnit).filter(CourseUnit.unit_id.in_(absorbed_ids)).all():
        if cu.course_id not in have_courses:
            db.add(CourseUnit(course_id=cu.course_id, unit_id=survivor_id))
            have_courses.add(cu.course_id)
            gained_courses += 1
    db.flush()

    # --- placecards -----------------------------------------------------------
    # Booking.unit_id is ON DELETE SET NULL, so this has to happen before the
    # absorbed rows go or their placecards become cards with no class.
    bookings = db.query(Booking).filter(Booking.unit_id.in_(absorbed_ids)).all()
    for b in bookings:
        b.unit_id = survivor_id
    moved_bookings = len(bookings)

    # --- lecturer preferences -------------------------------------------------
    # Also SET NULL. A preference to teach the absorbed class should follow it
    # to the survivor; class_name is left as the lecturer wrote it, since
    # rewriting it would lose what they actually asked for.
    prefs = db.query(StaffPreference).filter(StaffPreference.unit_id.in_(absorbed_ids)).all()
    for p in prefs:
        p.unit_id = survivor_id
    db.flush()

    # --- overlaps the move created -------------------------------------------
    # Repointing can leave the survivor with two placecards for one cohort at
    # the same time. That is a normal clash to resolve, but it should not be a
    # surprise, so it is counted and reported.
    overlaps = _count_overlaps(db, survivor_id)

    gained_codes: list[str] = []
    if merge_codes:
        have_codes = _codes(survivor)
        for i in absorbed_ids:
            for code in sorted(_codes(by_id[i])):
                if code not in have_codes:
                    have_codes.add(code)
                    gained_codes.append(code)
        if gained_codes:
            # Appended in the field's own format, preserving the survivor's
            # existing spelling rather than rewriting it from the normalised set.
            existing = (survivor.component_codes or "").strip().rstrip(",")
            added = ", ".join(c.upper() for c in gained_codes)
            survivor.component_codes = f"{existing}, {added}" if existing else added

    for unit in (by_id[i] for i in absorbed_ids):
        # Everything still hanging off these -- allowed rooms, competencies,
        # online counts, LAPs -- cascades away with them, by design.
        db.delete(unit)

    survivor.common_class = 0  # dealt with; stop it showing in the filter
    db.commit()

    return {
        "survivor_id": survivor_id,
        "survivor_name": survivor.name,
        "absorbed_count": len(absorbed_ids),
        "qualifications_gained": gained_quals,
        "groups_gained": gained_courses,
        "bookings_moved": moved_bookings,
        "preferences_moved": len(prefs),
        "overlaps_created": overlaps,
        "codes_gained": gained_codes,
        "summary": (
            f"Folded {len(absorbed_ids)} class(es) into {survivor.name}: "
            f"+{gained_quals} qualification(s), +{gained_courses} group(s), "
            f"{moved_bookings} placecard(s) moved"
            + (f"; {overlaps} overlap(s) to resolve" if overlaps else "")
        ),
    }


def _count_overlaps(db: Session, survivor_id: int) -> int:
    """Pairs of the survivor's placecards that now collide for one cohort."""
    rows = db.query(Booking).filter(Booking.unit_id == survivor_id).all()
    by_slot: dict[tuple, list[Booking]] = {}
    for b in rows:
        by_slot.setdefault((b.week_id, b.course_id, b.day), []).append(b)

    overlaps = 0
    for group in by_slot.values():
        ordered = sorted(group, key=lambda b: b.start_slot)
        for i, a in enumerate(ordered):
            for c in ordered[i + 1 :]:
                if c.start_slot >= a.end_slot:
                    break
                overlaps += 1
    return overlaps

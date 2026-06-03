"""Block delivery qualifications — intense 1–3 week scheduling."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .booking_sessions import SEMESTER_WEEKS, active_session_weeks
from .models import Booking, Course, Qualification

DELIVERY_REGULAR = "regular"
DELIVERY_BLOCK = "block"

MIN_BLOCK_WEEKS = 1
MAX_BLOCK_WEEKS = 3


def is_block_qualification(q: Qualification | None) -> bool:
    return q is not None and getattr(q, "delivery_mode", DELIVERY_REGULAR) == DELIVERY_BLOCK


def block_week_count(q: Qualification) -> int:
    """Legacy qualification-level default block length."""
    raw = getattr(q, "block_week_count", None)
    if raw is None:
        return MIN_BLOCK_WEEKS
    return max(MIN_BLOCK_WEEKS, min(MAX_BLOCK_WEEKS, int(raw)))


def block_start_semester_week(q: Qualification) -> int:
    """Legacy qualification-level default start week."""
    raw = getattr(q, "block_start_semester_week", None)
    if raw is None:
        return 1
    return max(1, min(SEMESTER_WEEKS, int(raw)))


def qualification_for_course(
    course: Course | None,
    session: Session | None = None,
) -> Qualification | None:
    if course is None or course.qualification_id is None:
        return None
    qual = getattr(course, "qualification", None)
    if qual is not None:
        return qual
    if session is None:
        from sqlalchemy.orm import object_session

        session = object_session(course)
    if session is not None:
        return session.get(Qualification, course.qualification_id)
    return None


def course_block_week_count(
    course: Course,
    qual: Qualification | None = None,
) -> int:
    raw = getattr(course, "block_week_count", None)
    if raw is not None:
        return max(MIN_BLOCK_WEEKS, min(MAX_BLOCK_WEEKS, int(raw)))
    if qual is None:
        qual = qualification_for_course(course)
    if qual is not None and is_block_qualification(qual):
        return block_week_count(qual)
    return MIN_BLOCK_WEEKS


def course_block_start_semester_week(
    course: Course,
    qual: Qualification | None = None,
) -> int:
    raw = getattr(course, "block_start_semester_week", None)
    if raw is not None:
        return max(1, min(SEMESTER_WEEKS, int(raw)))
    if qual is None:
        qual = qualification_for_course(course)
    if qual is not None:
        return block_start_semester_week(qual)
    return 1


def block_semester_weeks_for_course(
    course: Course,
    qual: Qualification | None = None,
) -> list[int]:
    qual = qual or qualification_for_course(course)
    if qual is None or not is_block_qualification(qual):
        return []
    start = course_block_start_semester_week(course, qual)
    count = course_block_week_count(course, qual)
    end = min(SEMESTER_WEEKS, start + count - 1)
    return list(range(start, end + 1))


def block_calendar_weeks_for_course(
    course: Course,
    qual: Qualification | None = None,
) -> list[int]:
    """Calendar semester weeks for a block cohort (works even if qual mode is out of sync)."""
    qual = qual or qualification_for_course(course)
    weeks = block_semester_weeks_for_course(course, qual)
    if weeks:
        return weeks
    if not (is_block_cohort(course) or looks_like_block_cohort_code(course.code)):
        return []
    start = course_block_start_semester_week(course, qual)
    count = course_block_week_count(course, qual)
    end = min(SEMESTER_WEEKS, start + count - 1)
    return list(range(start, end + 1))


@dataclass(frozen=True)
class BlockOverviewRow:
    course_id: int
    label: str
    tooltip: str
    calendar_weeks: list[int]


def all_block_cohort_courses(session: Session) -> list[Course]:
    """All block-delivery cohort courses in the session."""
    session.expire_all()
    courses = (
        session.query(Course)
        .filter(or_(Course.is_block_cohort == 1, Course.code.like("% Blk Grp%")))
        .order_by(Course.code)
        .all()
    )
    seen: set[int] = set()
    out: list[Course] = []
    for course in courses:
        if course.id in seen:
            continue
        seen.add(course.id)
        if looks_like_block_cohort_code(course.code) and not is_block_cohort(course):
            mark_block_cohort(course)
        out.append(course)
    if out:
        session.flush()
    return out


def all_block_overview_rows(session: Session) -> list[BlockOverviewRow]:
    """Rows for the overall block overview grid."""
    rows: list[BlockOverviewRow] = []
    for course in all_block_cohort_courses(session):
        qual = qualification_for_course(course, session)
        weeks = block_calendar_weeks_for_course(course, qual)
        if not weeks:
            continue
        qual_name = qual.name if qual is not None else "—"
        length = len(weeks)
        label = f"{qual_name} · {course.code}"
        tooltip = (
            f"{course.code}\n"
            f"Block length: {length} week{'s' if length != 1 else ''}\n"
            f"Semester weeks: W{weeks[0]}–W{weeks[-1]}"
        )
        rows.append(
            BlockOverviewRow(
                course_id=course.id,
                label=label,
                tooltip=tooltip,
                calendar_weeks=weeks,
            )
        )
    rows.sort(key=lambda r: r.label.lower())
    return rows


def block_week_index_for_semester_week(
    course: Course,
    semester_week: int,
    qual: Qualification | None = None,
) -> int | None:
    """Map a calendar semester week to a block week index (1-based) for a cohort."""
    weeks = block_calendar_weeks_for_course(course, qual)
    if semester_week not in weeks:
        return None
    return semester_week - weeks[0] + 1


def block_semester_weeks(q: Qualification) -> list[int]:
    """Calendar semester weeks using qualification defaults (legacy helper)."""
    if not is_block_qualification(q):
        return []
    start = block_start_semester_week(q)
    count = block_week_count(q)
    end = min(SEMESTER_WEEKS, start + count - 1)
    return list(range(start, end + 1))


def semester_week_for_block_booking(
    course: Course,
    block_week_index: int,
    qual: Qualification | None = None,
) -> int | None:
    """Map block week index (1-based) to a semester week for a cohort group."""
    qual = qual or qualification_for_course(course)
    if qual is None or not is_block_qualification(qual):
        return None
    count = course_block_week_count(course, qual)
    if block_week_index < 1 or block_week_index > count:
        return None
    return course_block_start_semester_week(course, qual) + block_week_index - 1


def block_delivery_summary(q: Qualification) -> str:
    if not is_block_qualification(q):
        return "Regular delivery"
    return "Block delivery — length and start week are set per group in the timetable view"


def block_sidebar_label(q: Qualification, session: Session | None = None) -> str:
    if not is_block_qualification(q):
        return q.name
    if session is None:
        return q.name
    courses = qualification_group_courses(session, q)
    if not courses:
        return q.name
    if len(courses) == 1:
        weeks = block_semester_weeks_for_course(courses[0], q)
        if not weeks:
            return q.name
        if len(weeks) == 1:
            return f"{q.name} · 1 wk W{weeks[0]}"
        return f"{q.name} · {len(weeks)} wks W{weeks[0]}–W{weeks[-1]}"
    return f"{q.name} · {len(courses)} groups"


def qualification_for_booking(booking: Booking, session: Session | None = None) -> Qualification | None:
    if booking.course is None:
        if session is None:
            from sqlalchemy.orm import object_session

            session = object_session(booking)
        if session is not None:
            course = session.get(Course, booking.course_id)
            return qualification_for_course(course, session)
        return None
    if booking.course.qualification_id is None:
        return None
    qual = getattr(booking.course, "qualification", None)
    if qual is not None:
        return qual
    if session is None:
        from sqlalchemy.orm import object_session

        session = object_session(booking)
    if session is not None:
        return session.get(Qualification, booking.course.qualification_id)
    return None


def semester_weeks_for_booking(booking: Booking, session: Session | None = None) -> set[int]:
    idx = getattr(booking, "block_week_index", None)
    if idx is not None:
        if session is None:
            from sqlalchemy.orm import object_session

            session = object_session(booking)
        course = booking.course
        if course is None and session is not None:
            course = session.get(Course, booking.course_id)
        if course is None:
            return set()
        qual = qualification_for_booking(booking, session)
        if qual is None or not is_block_qualification(qual):
            return set()
        sw = semester_week_for_block_booking(course, int(idx), qual)
        return {sw} if sw is not None else set()
    return set(active_session_weeks(booking))


def semester_weeks_overlap(
    a: Booking,
    b: Booking,
    session: Session | None = None,
) -> bool:
    return bool(semester_weeks_for_booking(a, session) & semester_weeks_for_booking(b, session))


def same_schedule_lane(a: Booking, b: Booking) -> bool:
    """True when two bookings share the same regular/block week context."""
    return getattr(a, "block_week_index", None) == getattr(b, "block_week_index", None)


def is_block_booking(booking: Booking) -> bool:
    return getattr(booking, "block_week_index", None) is not None


def group_letter(idx: int) -> str:
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA', etc."""
    s = ""
    n = idx
    while True:
        s = chr(ord("A") + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            return s


def qualification_group_code(qual_name: str, group_index: int) -> str:
    """Build the standard regular-delivery cohort code, e.g. 'CIV Cybr Stg1 GrpA'."""
    return f"{qual_name} Grp{group_letter(group_index)}"


def block_group_code(qual_name: str, group_index: int) -> str:
    """Build a block-delivery cohort code, e.g. 'CIV Cybr Stg1 Blk GrpA'."""
    return f"{qual_name} Blk Grp{group_letter(group_index)}"


def is_block_cohort(course: Course | None) -> bool:
    return course is not None and bool(getattr(course, "is_block_cohort", 0))


def looks_like_block_cohort_code(code: str | None) -> bool:
    """True when a course code uses the block cohort naming pattern."""
    return code is not None and " Blk Grp" in code


def mark_block_cohort(course: Course) -> None:
    """Persistently flag a course as a block-delivery cohort."""
    course.is_block_cohort = 1


def regular_qualification_group_courses(session: Session, qual: Qualification) -> list[Course]:
    """Regular semester cohort courses linked to a qualification."""
    session.expire_all()
    linked = (
        session.query(Course)
        .filter_by(qualification_id=qual.id, is_block_cohort=0)
        .order_by(Course.code)
        .all()
    )
    linked = [c for c in linked if not looks_like_block_cohort_code(c.code)]
    if linked:
        return linked

    escaped = qual.name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    prefix = f"{escaped} Grp"
    blk_prefix = f"{escaped} Blk Grp"
    return (
        session.query(Course)
        .filter(
            Course.qualification_id == qual.id,
            Course.code.like(f"{prefix}%", escape="\\"),
            ~Course.code.like(f"{blk_prefix}%", escape="\\"),
        )
        .order_by(Course.code)
        .all()
    )


def block_qualification_group_courses(session: Session, qual: Qualification) -> list[Course]:
    """Block-delivery cohort courses for a qualification."""
    session.expire_all()
    flagged = (
        session.query(Course)
        .filter_by(qualification_id=qual.id, is_block_cohort=1)
        .order_by(Course.code)
        .all()
    )
    if flagged:
        return flagged

    escaped = qual.name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    blk_prefix = f"{escaped} Blk Grp"
    misflagged = (
        session.query(Course)
        .filter(
            Course.qualification_id == qual.id,
            Course.code.like(f"{blk_prefix}%", escape="\\"),
        )
        .order_by(Course.code)
        .all()
    )
    for course in misflagged:
        mark_block_cohort(course)
    if misflagged:
        session.flush()
    return misflagged


def enable_block_delivery_mode(session: Session, qual: Qualification) -> None:
    """Mark a qualification as block delivery and ensure default timing fields."""
    qual.delivery_mode = DELIVERY_BLOCK
    if qual.block_week_count is None:
        qual.block_week_count = MIN_BLOCK_WEEKS
    if qual.block_start_semester_week is None:
        qual.block_start_semester_week = 1


def next_block_group_code(session: Session, qual_id: int) -> str | None:
    """Suggested code for the next block cohort on this qualification."""
    q = session.get(Qualification, qual_id)
    if q is None:
        return None
    return block_group_code(q.name, len(block_qualification_group_courses(session, q)))


def next_qualification_group_code(session: Session, qual_id: int) -> str | None:
    """Suggested code for the next regular cohort group on this qualification."""
    q = session.get(Qualification, qual_id)
    if q is None:
        return None
    return qualification_group_code(q.name, len(regular_qualification_group_courses(session, q)))


def qualification_group_courses(session: Session, qual: Qualification) -> list[Course]:
    """Cohort courses for a qualification (read-only; never mutates the database)."""
    if is_block_qualification(qual):
        return block_qualification_group_courses(session, qual)
    return regular_qualification_group_courses(session, qual)


def link_course_to_qualification(course: Course, qual_id: int) -> None:
    """Attach a cohort course to its qualification."""
    if course.qualification_id is None:
        course.qualification_id = qual_id


def init_course_block_defaults(course: Course, q: Qualification) -> None:
    """Ensure a block cohort course has length and start-week defaults."""
    if getattr(course, "block_week_count", None) is None:
        course.block_week_count = block_week_count(q)
    if getattr(course, "block_start_semester_week", None) is None:
        course.block_start_semester_week = block_start_semester_week(q)


def sync_qualification_num_groups(session: Session, qual_id: int) -> None:
    """Raise num_groups when regular cohort courses exceed the stored count."""
    q = session.get(Qualification, qual_id)
    if q is None:
        return
    n = (
        session.query(Course)
        .filter_by(qualification_id=qual_id, is_block_cohort=0)
        .count()
    )
    if n > (getattr(q, "num_groups", 1) or 1):
        q.num_groups = n


def clone_booking_for_course(src: Booking, course_id: int) -> Booking:
    """Copy a booking onto another course (all scheduling fields)."""
    return Booking(
        week_id=src.week_id,
        course_id=course_id,
        unit_id=src.unit_id,
        staff_id=src.staff_id,
        sfs_co_teacher_staff_id=getattr(src, "sfs_co_teacher_staff_id", None),
        sfs_co_teacher_in_term_1=getattr(src, "sfs_co_teacher_in_term_1", 0) or 0,
        sfs_co_teacher_in_term_2=getattr(src, "sfs_co_teacher_in_term_2", 0) or 0,
        room_id=src.room_id,
        day=src.day,
        start_slot=src.start_slot,
        end_slot=src.end_slot,
        notes=src.notes,
        external_id=src.external_id,
        in_term_1=src.in_term_1,
        in_term_2=src.in_term_2,
        online_student_count=getattr(src, "online_student_count", None),
        lock_time=getattr(src, "lock_time", 0) or 0,
        lock_staff=getattr(src, "lock_staff", 0) or 0,
        session_part=getattr(src, "session_part", 1) or 1,
        session_weeks=getattr(src, "session_weeks", None),
        block_week_index=getattr(src, "block_week_index", None),
    )


def _unique_block_group_code(session: Session, qual_name: str, group_index: int) -> str:
    """Return a free block cohort code, advancing the index if needed."""
    idx = group_index
    while True:
        code = block_group_code(qual_name, idx)
        if session.query(Course).filter_by(code=code).first() is None:
            return code
        idx += 1


def ensure_initial_block_group(session: Session, q: Qualification) -> Course:
    """Ensure a block qualification has exactly one initial block cohort."""
    existing = block_qualification_group_courses(session, q)
    if existing:
        course = existing[0]
        mark_block_cohort(course)
        init_course_block_defaults(course, q)
        session.flush()
        return course

    code = _unique_block_group_code(session, q.name, 0)
    existing_by_code = session.query(Course).filter_by(code=code).first()
    if existing_by_code is not None:
        existing_by_code.qualification_id = q.id
        mark_block_cohort(existing_by_code)
        init_course_block_defaults(existing_by_code, q)
        session.flush()
        return existing_by_code

    course = Course(
        code=code,
        qualification_id=q.id,
        is_block_cohort=1,
        timetable_session_id=q.timetable_session_id,
    )
    init_course_block_defaults(course, q)
    session.add(course)
    session.flush()
    mark_block_cohort(course)
    session.flush()
    return course


def create_block_delivery(session: Session, qual_id: int) -> tuple[Qualification, Course]:
    """Enable block delivery for a qualification and ensure one block cohort exists."""
    session.expire_all()
    q = session.get(Qualification, qual_id)
    if q is None:
        raise ValueError("Qualification not found")
    enable_block_delivery_mode(session, q)
    # Flush before ensure_initial_block_group: its queries call expire_all() and would
    # otherwise reload delivery_mode from the DB while it is still 'regular'.
    session.flush()
    course = ensure_initial_block_group(session, q)
    enable_block_delivery_mode(session, q)
    session.flush()
    session.commit()
    session.expire_all()
    return q, course


def remove_block_delivery(session: Session, qual_id: int) -> None:
    """Revert a qualification to regular delivery when it has no block cohorts."""
    q = session.get(Qualification, qual_id)
    if q is None:
        return
    q.delivery_mode = DELIVERY_REGULAR


def delete_block_group(session: Session, course_id: int) -> bool:
    """Delete a block cohort and its bookings.

    Returns True when the qualification was reverted to regular delivery
    because no block cohorts remain.
    """
    course = session.get(Course, course_id)
    if course is None or not (
        is_block_cohort(course) or looks_like_block_cohort_code(course.code)
    ):
        raise ValueError("Not a block group")
    mark_block_cohort(course)
    qual_id = course.qualification_id
    session.delete(course)
    session.flush()
    reverted = False
    if qual_id is not None:
        q = session.get(Qualification, qual_id)
        if q is not None and not block_qualification_group_courses(session, q):
            remove_block_delivery(session, qual_id)
            reverted = True
    session.commit()
    return reverted


def duplicate_block_group(
    session: Session,
    source_course_id: int,
    new_code: str,
    *,
    qual_id: int | None = None,
) -> tuple[Course, list[int]]:
    """Clone a block cohort and all its bookings; returns (new_course, booking_ids)."""
    from .sidebar_order import next_course_sidebar_order

    src = session.get(Course, source_course_id)
    if src is None:
        raise ValueError("Source course not found")
    if not is_block_cohort(src):
        raise ValueError("Source course is not a block group")
    effective_qual_id = src.qualification_id or qual_id
    if effective_qual_id is None:
        raise ValueError("Source course must belong to a qualification")
    q = session.get(Qualification, effective_qual_id)
    if q is None:
        raise ValueError("Qualification not found")
    if not is_block_qualification(q):
        if is_block_cohort(src) or looks_like_block_cohort_code(src.code):
            enable_block_delivery_mode(session, q)
            session.flush()
            q = session.get(Qualification, effective_qual_id)
        if q is None or not is_block_qualification(q):
            raise ValueError("Not a block qualification")
    if src.qualification_id is None:
        link_course_to_qualification(src, q.id)
    code = new_code.strip()
    if not code:
        raise ValueError("Group code is required")
    if session.query(Course).filter_by(code=code).first() is not None:
        raise ValueError(f"A course called {code!r} already exists")

    new_course = Course(
        code=code,
        name=src.name,
        qualification_id=q.id,
        is_block_cohort=1,
        timetable_session_id=src.timetable_session_id,
        timetable_locked=getattr(src, "timetable_locked", 0) or 0,
        sidebar_order=next_course_sidebar_order(session),
        block_week_count=course_block_week_count(src, q),
        block_start_semester_week=course_block_start_semester_week(src, q),
    )
    session.add(new_course)
    session.flush()

    cloned_ids: list[int] = []
    for b in session.query(Booking).filter_by(course_id=src.id).all():
        nb = clone_booking_for_course(b, new_course.id)
        session.add(nb)
        session.flush()
        cloned_ids.append(nb.id)

    session.commit()
    session.expire_all()
    return new_course, cloned_ids


def block_booking_label(booking: Booking, session: Session | None = None) -> str | None:
    """Short export label for block bookings, e.g. 'Blk W2 · Sem W9'."""
    idx = getattr(booking, "block_week_index", None)
    if idx is None:
        return None
    if session is None:
        from sqlalchemy.orm import object_session

        session = object_session(booking)
    course = booking.course
    if course is None and session is not None:
        course = session.get(Course, booking.course_id)
    if course is None:
        return f"Blk W{idx}"
    qual = qualification_for_booking(booking, session)
    sw = semester_week_for_block_booking(course, int(idx), qual)
    if sw is None:
        return f"Blk W{idx}"
    return f"Blk W{idx} · Sem W{sw}"

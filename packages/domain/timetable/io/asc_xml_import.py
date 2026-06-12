"""Import staff, rooms, qualifications, classes, and bookings from aSc 2012 XML."""
from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ..constants import NUM_DAYS, time_to_slot
from ..core.models import (
    Booking,
    Course,
    CourseUnit,
    Qualification,
    Room,
    StaffCompetency,
    Unit,
    UnitAllowedRoom,
    UnitQualification,
)
from ..core.unit_brackets import apply_unit_bracket_fields_from_names
from .asc_import import (
    AscImportReport,
    _asc_periods_to_slots,
    _create_kwargs,
    _ensure_course_unit,
    _ensure_qualification,
    _ensure_room,
    _ensure_staff,
    _find_room,
    _norm,
    _parse_asc_time,
    _parse_length,
    _scoped_filter_by,
    _unit_storage_name,
)
from .visual_import_session import VisualImportContext


def _attr(elem: ET.Element | None, name: str) -> str | None:
    if elem is None:
        return None
    raw = elem.get(name)
    if raw is None:
        return None
    text = html.unescape(str(raw).strip())
    return text or None


def _split_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _section_items(root: ET.Element, section_tag: str, item_tag: str) -> list[ET.Element]:
    section = root.find(section_tag)
    if section is None:
        return []
    return section.findall(item_tag)


def is_asc_export_xml(path: str | Path) -> bool:
    """Return True when the file looks like an aSc Timetables 2012 XML export."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return False
    if root.tag != "timetable":
        return False
    display = (root.get("displayname") or "").lower()
    if "asc" in display and "xml" in display:
        return True
    return (
        root.find("teachers") is not None
        and root.find("classrooms") is not None
        and root.find("classes") is not None
        and root.find("lessons") is not None
        and root.find("cards") is not None
    )


def _parse_asc_xml_period_map(root: ET.Element) -> dict[int, tuple[int, int]]:
    """Build aSc period number → (start_slot, end_slot) from XML bell times."""
    section = root.find("periods")
    if section is None:
        return {}
    mapping: dict[int, tuple[int, int]] = {}
    for elem in section.findall("period"):
        period_raw = _attr(elem, "period")
        start_raw = _attr(elem, "starttime")
        end_raw = _attr(elem, "endtime")
        if not period_raw or not start_raw or not end_raw:
            continue
        try:
            period = int(float(period_raw))
            start_slot = time_to_slot(_parse_asc_time(start_raw))
            end_slot = time_to_slot(_parse_asc_time(end_raw))
        except (TypeError, ValueError):
            continue
        mapping[period] = (start_slot, end_slot)
    return mapping


def _day_index_from_pattern(days: str) -> int | None:
    pattern = (days or "").strip()
    for i in range(min(len(pattern), NUM_DAYS)):
        if pattern[i] == "1":
            return i
    return None


def _term_flags(terms: str | None) -> tuple[bool, bool]:
    t = (terms or "11").strip()
    if t == "10":
        return True, False
    if t == "01":
        return False, True
    return True, True


def _merge_period_runs(periods: list[int]) -> list[tuple[int, int]]:
    if not periods:
        return []
    ordered = sorted(set(periods))
    runs: list[tuple[int, int]] = []
    start = end = ordered[0]
    for period in ordered[1:]:
        if period == end + 1:
            end = period
            continue
        runs.append((start, end))
        start = end = period
    runs.append((start, end))
    return runs


def _unique_room_code(
    *,
    short: str | None,
    name: str | None,
    room_id: str,
    seen: dict[str, int],
) -> str:
    for candidate in (short, name, room_id):
        if not candidate:
            continue
        key = _norm(candidate)
        if key not in seen:
            seen[key] = 1
            return candidate.strip()
    base = (name or short or room_id).strip()
    seen[base] = seen.get(base, 0) + 1
    if seen[base] == 1:
        return base
    return f"{base} ({room_id[:8]})"


@dataclass(frozen=True)
class _XmlCard:
    lesson_id: str
    days: str
    period: int
    room_id: str | None
    terms: str | None


def _rooms_for_classroom_ids(
    session: Session,
    timetable_session_id: int | None,
    classroom_ids_raw: str | None,
    *,
    rooms_by_id: dict[str, str],
    room_names_by_id: dict[str, str],
    room_cache: dict[str, Room],
    rep: AscImportReport,
) -> list[Room]:
    rooms: list[Room] = []
    seen_room_ids: set[int] = set()
    for room_id in _split_ids(classroom_ids_raw):
        code = rooms_by_id.get(room_id)
        if not code:
            continue
        room = _find_room(session, timetable_session_id, code)
        if room is None:
            room = _ensure_room(
                session,
                timetable_session_id,
                code=code,
                name=room_names_by_id.get(room_id),
                rep=rep,
                cache=room_cache,
            )
        if room is not None and room.id not in seen_room_ids:
            seen_room_ids.add(room.id)
            rooms.append(room)
    return rooms


def _parse_cards(root: ET.Element) -> list[_XmlCard]:
    cards: list[_XmlCard] = []
    section = root.find("cards")
    if section is None:
        return cards
    for elem in section.findall("card"):
        lesson_id = _attr(elem, "lessonid")
        period_raw = _attr(elem, "period")
        days = _attr(elem, "days")
        if not lesson_id or not period_raw or not days:
            continue
        try:
            period = int(float(period_raw))
        except ValueError:
            continue
        room_ids = _split_ids(_attr(elem, "classroomids"))
        cards.append(
            _XmlCard(
                lesson_id=lesson_id,
                days=days,
                period=period,
                room_id=room_ids[0] if room_ids else None,
                terms=_attr(elem, "terms"),
            )
        )
    return cards


def _ensure_cohort_unit_from_lesson(
    session: Session,
    *,
    class_id: str,
    subject_id: str,
    lesson: ET.Element,
    class_names: dict[str, str],
    class_shorts: dict[str, str],
    subjects_by_id: dict[str, tuple[str, str]],
    timetable_session_id: int | None,
    rep: AscImportReport,
    qual_cache: dict[str, Qualification],
    course_cache: dict[str, Course],
    unit_cache: dict[tuple[str, str], Unit],
    unit_qual_linked: set[tuple[int, int]],
    staff_comp_linked: set[tuple[int, int]],
    unit_room_linked: set[tuple[int, int]],
    teachers_by_id: dict[str, str],
    rooms_by_id: dict[str, str],
    room_names_by_id: dict[str, str],
    room_cache: dict[str, Room],
    staff_cache: dict[str, object],
) -> tuple[Course | None, Unit | None]:
    """Ensure qualification, unit, and constraint links for one cohort on a lesson."""
    class_name = class_names.get(class_id)
    subject = subjects_by_id.get(subject_id)
    if not class_name or not subject:
        return None, None
    subject_code, subject_title = subject
    qual_key = _norm(class_name)
    if qual_key not in qual_cache:
        _ensure_qualification(
            session,
            timetable_session_id,
            name=class_name,
            course_code_hint=class_shorts.get(class_id),
            rep=rep,
            qual_cache=qual_cache,
            course_cache=course_cache,
        )
    qual = qual_cache.get(qual_key)
    course = course_cache.get(qual_key)
    if qual is None or course is None:
        return None, None

    subj_key = _norm(subject_code)
    unit_key = (qual_key, subj_key)
    storage_name = _unit_storage_name(
        subject_code,
        subject_title,
        class_name,
        class_short=class_shorts.get(class_id),
    )
    unit = unit_cache.get(unit_key)
    if unit is None:
        unit = _scoped_filter_by(session, Unit, timetable_session_id, name=storage_name).first()
        if unit is None:
            unit = Unit(
                **_create_kwargs(
                    Unit,
                    timetable_session_id,
                    name=storage_name,
                    component_codes=subject_code,
                )
            )
            session.add(unit)
            session.flush()
            rep.classes_created += 1
        else:
            rep.classes_updated += 1
        unit_cache[unit_key] = unit
    else:
        rep.classes_updated += 1

    if not unit.component_codes:
        unit.component_codes = subject_code
    length = _parse_length(_attr(lesson, "periodspercard"))
    if length and not unit.length_slots:
        unit.length_slots = length

    qual_link = (unit.id, qual.id)
    if qual_link not in unit_qual_linked:
        unit_qual_linked.add(qual_link)
        if not session.query(UnitQualification).filter_by(
            unit_id=unit.id, qualification_id=qual.id
        ).first():
            session.add(UnitQualification(unit_id=unit.id, qualification_id=qual.id))
            rep.class_qual_links_added += 1

    teacher_ids = _split_ids(_attr(lesson, "teacherids"))
    if teacher_ids:
        teacher_name = teachers_by_id.get(teacher_ids[0])
        if teacher_name:
            staff = _ensure_staff(session, timetable_session_id, teacher_name, rep, staff_cache)
            if staff:
                comp_link = (staff.id, unit.id)
                if comp_link not in staff_comp_linked:
                    staff_comp_linked.add(comp_link)
                    if not session.query(StaffCompetency).filter_by(
                        staff_id=staff.id, unit_id=unit.id
                    ).first():
                        session.add(StaffCompetency(staff_id=staff.id, unit_id=unit.id))
                        rep.lecturer_links_added += 1

    for room in _rooms_for_classroom_ids(
        session,
        timetable_session_id,
        _attr(lesson, "classroomids"),
        rooms_by_id=rooms_by_id,
        room_names_by_id=room_names_by_id,
        room_cache=room_cache,
        rep=rep,
    ):
        room_link = (unit.id, room.id)
        if room_link in unit_room_linked:
            continue
        unit_room_linked.add(room_link)
        if not session.query(UnitAllowedRoom).filter_by(unit_id=unit.id, room_id=room.id).first():
            session.add(UnitAllowedRoom(unit_id=unit.id, room_id=room.id))
            rep.room_links_added += 1

    return course, unit


def import_asc_xml_export(
    session: Session,
    path: str | Path,
    *,
    timetable_session_id: int | None = None,
) -> AscImportReport:
    if not is_asc_export_xml(path):
        raise ValueError(
            "File does not look like an aSc Timetables XML export "
            "(expected <timetable> with teachers, lessons, and cards)."
        )

    rep = AscImportReport()
    root = ET.parse(path).getroot()

    staff_cache = {}
    room_cache: dict[str, object] = {}
    qual_cache = {}
    course_cache = {}
    unit_cache: dict[tuple[str, str], Unit] = {}
    unit_qual_linked: set[tuple[int, int]] = set()
    staff_comp_linked: set[tuple[int, int]] = set()
    unit_room_linked: set[tuple[int, int]] = set()

    teachers_by_id: dict[str, str] = {}
    for elem in _section_items(root, "teachers", "teacher"):
        tid = _attr(elem, "id")
        name = _attr(elem, "name")
        if tid and name:
            teachers_by_id[tid] = name
            _ensure_staff(session, timetable_session_id, name, rep, staff_cache)

    rooms_by_id: dict[str, str] = {}
    room_names_by_id: dict[str, str] = {}
    seen_room_codes: dict[str, int] = {}
    for elem in _section_items(root, "classrooms", "classroom"):
        rid = _attr(elem, "id")
        if not rid:
            continue
        short = _attr(elem, "short")
        name = _attr(elem, "name")
        code = _unique_room_code(short=short, name=name, room_id=rid, seen=seen_room_codes)
        rooms_by_id[rid] = code
        room_names_by_id[rid] = name or code
        _ensure_room(
            session,
            timetable_session_id,
            code=code,
            name=name,
            rep=rep,
            cache=room_cache,
        )

    class_names: dict[str, str] = {}
    class_shorts: dict[str, str] = {}
    for elem in _section_items(root, "classes", "class"):
        cid = _attr(elem, "id")
        name = _attr(elem, "name")
        short = _attr(elem, "short")
        if not cid or not name:
            continue
        class_names[cid] = name
        class_shorts[cid] = short or name
        qual_key = _norm(name)
        _ensure_qualification(
            session,
            timetable_session_id,
            name=name,
            course_code_hint=short,
            rep=rep,
            qual_cache=qual_cache,
            course_cache=course_cache,
        )

    subjects_by_id: dict[str, tuple[str, str]] = {}
    for elem in _section_items(root, "subjects", "subject"):
        sid = _attr(elem, "id")
        name = _attr(elem, "name")
        short = _attr(elem, "short") or name
        if sid and short:
            subjects_by_id[sid] = (short, name or short)

    lessons_by_id: dict[str, ET.Element] = {}
    lessons_section = root.find("lessons")
    if lessons_section is not None:
        for elem in lessons_section.findall("lesson"):
            lid = _attr(elem, "id")
            if lid:
                lessons_by_id[lid] = elem

    for _lid, elem in lessons_by_id.items():
        class_ids = _split_ids(_attr(elem, "classids"))
        subject_id = _attr(elem, "subjectid")
        if not class_ids or not subject_id:
            continue
        for class_id in class_ids:
            _ensure_cohort_unit_from_lesson(
                session,
                class_id=class_id,
                subject_id=subject_id,
                lesson=elem,
                class_names=class_names,
                class_shorts=class_shorts,
                subjects_by_id=subjects_by_id,
                timetable_session_id=timetable_session_id,
                rep=rep,
                qual_cache=qual_cache,
                course_cache=course_cache,
                unit_cache=unit_cache,
                unit_qual_linked=unit_qual_linked,
                staff_comp_linked=staff_comp_linked,
                unit_room_linked=unit_room_linked,
                teachers_by_id=teachers_by_id,
                rooms_by_id=rooms_by_id,
                room_names_by_id=room_names_by_id,
                room_cache=room_cache,
                staff_cache=staff_cache,
            )

    cards = _parse_cards(root)
    period_map = _parse_asc_xml_period_map(root)
    if cards:
        ctx = VisualImportContext(timetable_session_id)
        week = ctx.first_week(session)
        session.query(Booking).filter(Booking.week_id == week.id).delete()

        grouped: dict[tuple[str, str, str | None], list[_XmlCard]] = defaultdict(list)
        for card in cards:
            grouped[(card.lesson_id, card.days, card.terms)].append(card)

        course_unit_linked: set[tuple[int, int]] = set()
        for (lesson_id, days, terms), card_rows in grouped.items():
            lesson = lessons_by_id.get(lesson_id)
            if lesson is None:
                rep.warnings.append(f"Card references unknown lesson {lesson_id!r}")
                continue
            class_ids = _split_ids(_attr(lesson, "classids"))
            subject_id = _attr(lesson, "subjectid")
            if not class_ids or not subject_id:
                continue
            subject = subjects_by_id.get(subject_id)
            if not subject:
                continue
            subject_code, _subject_title = subject
            subj_key = _norm(subject_code)

            day_idx = _day_index_from_pattern(days)
            if day_idx is None:
                rep.warnings.append(f"Cards for lesson {lesson_id}: unmapped day pattern {days!r}")
                continue

            terms = terms or card_rows[0].terms
            in_term_1, in_term_2 = _term_flags(terms)

            for start_period, end_period in _merge_period_runs([c.period for c in card_rows]):
                slot_range = _asc_periods_to_slots(
                    start_period,
                    end_period,
                    period_map=period_map or None,
                )
                if slot_range is None:
                    rep.warnings.append(
                        f"Cards for lesson {lesson_id}: invalid period range "
                        f"{start_period}-{end_period} on day {days!r}"
                    )
                    continue
                start_slot, end_slot = slot_range

                staff_id = None
                teacher_ids = _split_ids(_attr(lesson, "teacherids"))
                if teacher_ids:
                    teacher_name = teachers_by_id.get(teacher_ids[0])
                    if teacher_name:
                        staff = _ensure_staff(session, timetable_session_id, teacher_name, rep, staff_cache)
                        staff_id = staff.id if staff else None

                room_id = None
                card_room_ids = next((c.room_id for c in card_rows if c.room_id), None)
                lesson_room_ids = _attr(lesson, "classroomids")
                resolved_rooms = _rooms_for_classroom_ids(
                    session,
                    timetable_session_id,
                    card_room_ids or lesson_room_ids,
                    rooms_by_id=rooms_by_id,
                    room_names_by_id=room_names_by_id,
                    room_cache=room_cache,
                    rep=rep,
                )
                if resolved_rooms:
                    room_id = resolved_rooms[0].id

                cohorts_added = 0
                for class_id in class_ids:
                    class_name = class_names.get(class_id)
                    if not class_name:
                        continue
                    qual_key = _norm(class_name)
                    course = course_cache.get(qual_key)
                    unit = unit_cache.get((qual_key, subj_key))
                    if course is None or unit is None:
                        course, unit = _ensure_cohort_unit_from_lesson(
                            session,
                            class_id=class_id,
                            subject_id=subject_id,
                            lesson=lesson,
                            class_names=class_names,
                            class_shorts=class_shorts,
                            subjects_by_id=subjects_by_id,
                            timetable_session_id=timetable_session_id,
                            rep=rep,
                            qual_cache=qual_cache,
                            course_cache=course_cache,
                            unit_cache=unit_cache,
                            unit_qual_linked=unit_qual_linked,
                            staff_comp_linked=staff_comp_linked,
                            unit_room_linked=unit_room_linked,
                            teachers_by_id=teachers_by_id,
                            rooms_by_id=rooms_by_id,
                            room_names_by_id=room_names_by_id,
                            room_cache=room_cache,
                            staff_cache=staff_cache,
                        )
                    if course is None or unit is None:
                        rep.warnings.append(
                            f"Cards for lesson {lesson_id}: no course/unit for "
                            f"{subject_code!r}/{class_name!r}"
                        )
                        continue

                    _ensure_course_unit(session, course.id, unit.id, course_unit_linked)
                    session.add(
                        Booking(
                            week_id=week.id,
                            course_id=course.id,
                            unit_id=unit.id,
                            staff_id=staff_id,
                            room_id=room_id,
                            day=day_idx,
                            start_slot=start_slot,
                            end_slot=end_slot,
                            in_term_1=1 if in_term_1 else 0,
                            in_term_2=1 if in_term_2 else 0,
                        )
                    )
                    rep.bookings_created += 1
                    cohorts_added += 1
                if cohorts_added == 0:
                    rep.warnings.append(
                        f"Cards for lesson {lesson_id}: no participating cohorts could be scheduled"
                    )

    apply_unit_bracket_fields_from_names(session)
    session.commit()
    return rep

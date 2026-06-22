"""Session-scoped backup serialize/deserialize for multi-tenant web."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from timetable.core.combined_class import apply_combined_class_detection
from timetable.core.models import (
    Booking,
    ChangeLogEntry,
    Course,
    CourseUnit,
    Qualification,
    QualificationTimeWindow,
    Room,
    Semester,
    Staff,
    StaffAvailability,
    StaffCompetency,
    StaffPreference,
    StaffQualificationOnlineStudents,
    StaffUnitOnlineStudents,
    Unit,
    UnitAllowedRoom,
    UnitQualification,
    Week,
)
from timetable.core.tenancy_models import TimetableSession
from timetable.core.unit_brackets import apply_unit_bracket_fields_from_names

from .violation_cache import invalidate_session_violations
from timetable.io.backup_payload import PAYLOAD_VERSION, _prepare_units_for_restore

from .session_seed import seed_timetable_session_data


def _semester_ids(db: Session, timetable_session_id: int) -> list[int]:
    return [
        s.id
        for s in db.query(Semester.id)
        .filter(Semester.timetable_session_id == timetable_session_id)
        .all()
    ]


def _week_ids(db: Session, timetable_session_id: int) -> list[int]:
    sem_ids = _semester_ids(db, timetable_session_id)
    if not sem_ids:
        return []
    return [w.id for w in db.query(Week.id).filter(Week.semester_id.in_(sem_ids)).all()]


def _course_ids(db: Session, timetable_session_id: int) -> set[int]:
    return {
        c.id
        for c in db.query(Course.id).filter(Course.timetable_session_id == timetable_session_id).all()
    }


def _unit_ids(db: Session, timetable_session_id: int) -> set[int]:
    return {
        u.id for u in db.query(Unit.id).filter(Unit.timetable_session_id == timetable_session_id).all()
    }


def _staff_ids(db: Session, timetable_session_id: int) -> set[int]:
    return {
        s.id for s in db.query(Staff.id).filter(Staff.timetable_session_id == timetable_session_id).all()
    }


def _room_ids(db: Session, timetable_session_id: int) -> set[int]:
    return {
        r.id for r in db.query(Room.id).filter(Room.timetable_session_id == timetable_session_id).all()
    }


def _qualification_ids(db: Session, timetable_session_id: int) -> set[int]:
    return {
        q.id
        for q in db.query(Qualification.id)
        .filter(Qualification.timetable_session_id == timetable_session_id)
        .all()
    }


def clear_session_data(db: Session, timetable_session_id: int) -> None:
    """Remove timetable entities for one web session (keeps semester/week shell)."""
    week_ids = _week_ids(db, timetable_session_id)
    course_ids = _course_ids(db, timetable_session_id)
    unit_ids = _unit_ids(db, timetable_session_id)
    staff_ids = _staff_ids(db, timetable_session_id)
    qual_ids = _qualification_ids(db, timetable_session_id)

    if week_ids:
        db.query(Booking).filter(Booking.week_id.in_(week_ids)).delete(synchronize_session=False)

    if staff_ids:
        db.query(StaffAvailability).filter(StaffAvailability.staff_id.in_(staff_ids)).delete(
            synchronize_session=False
        )
        db.query(StaffPreference).filter(StaffPreference.staff_id.in_(staff_ids)).delete(
            synchronize_session=False
        )
        db.query(StaffCompetency).filter(StaffCompetency.staff_id.in_(staff_ids)).delete(
            synchronize_session=False
        )
        db.query(StaffQualificationOnlineStudents).filter(
            StaffQualificationOnlineStudents.staff_id.in_(staff_ids)
        ).delete(synchronize_session=False)
        db.query(StaffUnitOnlineStudents).filter(
            StaffUnitOnlineStudents.staff_id.in_(staff_ids)
        ).delete(synchronize_session=False)

    if qual_ids:
        db.query(QualificationTimeWindow).filter(
            QualificationTimeWindow.qualification_id.in_(qual_ids)
        ).delete(synchronize_session=False)

    if unit_ids:
        db.query(UnitQualification).filter(UnitQualification.unit_id.in_(unit_ids)).delete(
            synchronize_session=False
        )
        db.query(UnitAllowedRoom).filter(UnitAllowedRoom.unit_id.in_(unit_ids)).delete(
            synchronize_session=False
        )

    if course_ids:
        db.query(CourseUnit).filter(CourseUnit.course_id.in_(course_ids)).delete(
            synchronize_session=False
        )

    db.query(ChangeLogEntry).filter(
        ChangeLogEntry.timetable_session_id == timetable_session_id
    ).delete(synchronize_session=False)

    db.query(Course).filter(Course.timetable_session_id == timetable_session_id).update(
        {Course.qualification_id: None}
    )
    db.flush()
    db.query(Course).filter(Course.timetable_session_id == timetable_session_id).delete(
        synchronize_session=False
    )
    db.query(Unit).filter(Unit.timetable_session_id == timetable_session_id).delete(
        synchronize_session=False
    )
    db.query(Qualification).filter(
        Qualification.timetable_session_id == timetable_session_id
    ).delete(synchronize_session=False)
    db.query(Staff).filter(Staff.timetable_session_id == timetable_session_id).delete(
        synchronize_session=False
    )
    db.query(Room).filter(Room.timetable_session_id == timetable_session_id).delete(
        synchronize_session=False
    )
    db.flush()


def serialize_session(db: Session, timetable_session_id: int) -> dict[str, Any]:
    """Build backup payload for one web session."""
    qual_ids = _qualification_ids(db, timetable_session_id)
    unit_ids = _unit_ids(db, timetable_session_id)
    course_ids = _course_ids(db, timetable_session_id)
    staff_ids = _staff_ids(db, timetable_session_id)
    room_ids = _room_ids(db, timetable_session_id)
    week_ids = _week_ids(db, timetable_session_id)

    quals = (
        db.query(Qualification)
        .filter(Qualification.timetable_session_id == timetable_session_id)
        .order_by(Qualification.id)
        .all()
    )
    units = (
        db.query(Unit)
        .filter(Unit.timetable_session_id == timetable_session_id)
        .order_by(Unit.id)
        .all()
    )
    courses = (
        db.query(Course)
        .filter(Course.timetable_session_id == timetable_session_id)
        .order_by(Course.id)
        .all()
    )
    staff = (
        db.query(Staff)
        .filter(Staff.timetable_session_id == timetable_session_id)
        .order_by(Staff.id)
        .all()
    )
    rooms = (
        db.query(Room)
        .filter(Room.timetable_session_id == timetable_session_id)
        .order_by(Room.id)
        .all()
    )

    return {
        "version": PAYLOAD_VERSION,
        "qualifications": [
            {
                "id": q.id,
                "name": q.name,
                "num_groups": getattr(q, "num_groups", 1) or 1,
                "schedule_period": getattr(q, "schedule_period", None) or "day",
                "delivery_mode": getattr(q, "delivery_mode", None) or "regular",
                "block_week_count": getattr(q, "block_week_count", None),
                "block_start_semester_week": getattr(q, "block_start_semester_week", None),
            }
            for q in quals
        ],
        "qualification_time_windows": [
            {
                "qualification_id": w.qualification_id,
                "day": w.day,
                "start_slot": w.start_slot,
                "end_slot": w.end_slot,
            }
            for w in db.query(QualificationTimeWindow)
            .filter(QualificationTimeWindow.qualification_id.in_(qual_ids or [-1]))
            .all()
        ],
        "courses": [
            {
                "id": c.id,
                "code": c.code,
                "name": c.name,
                "qualification_id": c.qualification_id,
                "timetable_locked": getattr(c, "timetable_locked", 0) or 0,
                "sidebar_order": getattr(c, "sidebar_order", 0) or 0,
                "block_week_count": getattr(c, "block_week_count", None),
                "block_start_semester_week": getattr(c, "block_start_semester_week", None),
                "is_block_cohort": getattr(c, "is_block_cohort", 0) or 0,
            }
            for c in courses
        ],
        "units": [
            {
                "id": u.id,
                "name": u.name,
                "length_slots": u.length_slots,
                "component_codes": u.component_codes,
                "required_room_type": u.required_room_type,
                "required_capacity": u.required_capacity,
                "double_session": getattr(u, "double_session", 0) or 0,
                "double_session_same_day": getattr(u, "double_session_same_day", None),
                "double_session_first_slots": getattr(u, "double_session_first_slots", None),
            }
            for u in units
        ],
        "unit_qualifications": [
            {"unit_id": uq.unit_id, "qualification_id": uq.qualification_id}
            for uq in db.query(UnitQualification)
            .filter(UnitQualification.unit_id.in_(unit_ids or [-1]))
            .all()
        ],
        "unit_allowed_rooms": [
            {"unit_id": ur.unit_id, "room_id": ur.room_id}
            for ur in db.query(UnitAllowedRoom)
            .filter(UnitAllowedRoom.unit_id.in_(unit_ids or [-1]))
            .all()
        ],
        "course_units": [
            {"course_id": cu.course_id, "unit_id": cu.unit_id}
            for cu in db.query(CourseUnit)
            .filter(CourseUnit.course_id.in_(course_ids or [-1]))
            .all()
        ],
        "staff": [
            {
                "id": s.id,
                "name": s.name,
                "cost_centre": getattr(s, "cost_centre", None),
                "max_hours_per_week": s.max_hours_per_week,
                "non_teaching_day": s.non_teaching_day,
                "fte": getattr(s, "fte", None),
                "ot_hours": getattr(s, "ot_hours", None),
                "development_project_hours": getattr(s, "development_project_hours", None),
                "development_project_description": getattr(
                    s, "development_project_description", None
                ),
                "tae_hours": getattr(s, "tae_hours", None),
                "supervision_hours": getattr(s, "supervision_hours", None),
                "default_online_students_per_class": getattr(
                    s, "default_online_students_per_class", None
                ),
                "timetable_locked": getattr(s, "timetable_locked", 0) or 0,
                "sidebar_order": getattr(s, "sidebar_order", 0) or 0,
            }
            for s in staff
        ],
        "staff_qualification_online_students": [
            {
                "staff_id": row.staff_id,
                "qualification_id": row.qualification_id,
                "student_count": row.student_count,
            }
            for row in db.query(StaffQualificationOnlineStudents)
            .filter(StaffQualificationOnlineStudents.staff_id.in_(staff_ids or [-1]))
            .all()
        ],
        "staff_unit_online_students": [
            {
                "staff_id": row.staff_id,
                "unit_id": row.unit_id,
                "student_count": row.student_count,
            }
            for row in db.query(StaffUnitOnlineStudents)
            .filter(StaffUnitOnlineStudents.staff_id.in_(staff_ids or [-1]))
            .all()
        ],
        "staff_preferences": [
            {
                "id": p.id,
                "staff_id": p.staff_id,
                "priority": p.priority,
                "slot_number": p.slot_number,
                "qualification_name": p.qualification_name,
                "class_name": p.class_name,
                "unit_id": p.unit_id,
            }
            for p in db.query(StaffPreference)
            .filter(StaffPreference.staff_id.in_(staff_ids or [-1]))
            .order_by(StaffPreference.id)
            .all()
        ],
        "staff_competencies": [
            {"staff_id": sc.staff_id, "unit_id": sc.unit_id}
            for sc in db.query(StaffCompetency)
            .filter(StaffCompetency.staff_id.in_(staff_ids or [-1]))
            .all()
        ],
        "staff_availability": [
            {
                "id": a.id,
                "staff_id": a.staff_id,
                "day": a.day,
                "start_slot": a.start_slot,
                "end_slot": a.end_slot,
            }
            for a in db.query(StaffAvailability)
            .filter(StaffAvailability.staff_id.in_(staff_ids or [-1]))
            .all()
        ],
        "rooms": [
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "room_type": r.room_type,
                "capacity": r.capacity,
            }
            for r in rooms
        ],
        "bookings": [
            {
                "id": b.id,
                "course_id": b.course_id,
                "unit_id": b.unit_id,
                "staff_id": b.staff_id,
                "sfs_co_teacher_staff_id": getattr(b, "sfs_co_teacher_staff_id", None),
                "sfs_co_teacher_in_term_1": int(getattr(b, "sfs_co_teacher_in_term_1", 0)),
                "sfs_co_teacher_in_term_2": int(getattr(b, "sfs_co_teacher_in_term_2", 0)),
                "room_id": b.room_id,
                "day": b.day,
                "start_slot": b.start_slot,
                "end_slot": b.end_slot,
                "notes": b.notes,
                "external_id": b.external_id,
                "in_term_1": int(getattr(b, "in_term_1", 1)),
                "in_term_2": int(getattr(b, "in_term_2", 1)),
                "online_student_count": getattr(b, "online_student_count", None),
                "lock_time": getattr(b, "lock_time", 0) or 0,
                "lock_staff": getattr(b, "lock_staff", 0) or 0,
                "session_part": getattr(b, "session_part", 1) or 1,
                "session_weeks": getattr(b, "session_weeks", None),
                "block_week_index": getattr(b, "block_week_index", None),
                "combined_class_group_id": getattr(b, "combined_class_group_id", None),
            }
            for b in db.query(Booking)
            .filter(Booking.week_id.in_(week_ids or [-1]))
            .order_by(Booking.id)
            .all()
        ],
    }


def _map_id(id_map: dict[int, int], old: int | None) -> int | None:
    if old is None:
        return None
    return id_map[old]


def restore_session(db: Session, timetable_session_id: int, payload: dict[str, Any]) -> dict[str, int]:
    """Replace session timetable data from a desktop-compatible backup payload.

    Desktop exports preserve entity ids from a single SQLite file. On Postgres those
    ids are global, so we allocate fresh ids and remap foreign keys on import.
    """
    if not isinstance(payload, dict) or payload.get("version") not in (PAYLOAD_VERSION,):
        raise ValueError(
            f"Unknown payload version: {payload.get('version') if isinstance(payload, dict) else '?'}"
        )

    clear_session_data(db, timetable_session_id)

    qual_map: dict[int, int] = {}
    for q in payload.get("qualifications", []):
        row = Qualification(
            timetable_session_id=timetable_session_id,
            name=q["name"],
            num_groups=q.get("num_groups", 1) or 1,
            schedule_period=q.get("schedule_period") or "day",
            delivery_mode=q.get("delivery_mode") or "regular",
            block_week_count=q.get("block_week_count"),
            block_start_semester_week=q.get("block_start_semester_week"),
        )
        db.add(row)
        db.flush()
        qual_map[q["id"]] = row.id

    unit_map: dict[int, int] = {}
    for u in _prepare_units_for_restore(payload.get("units", [])):
        row = Unit(
            timetable_session_id=timetable_session_id,
            name=u["name"],
            length_slots=u.get("length_slots"),
            component_codes=u.get("component_codes"),
            required_room_type=u.get("required_room_type"),
            required_capacity=u.get("required_capacity"),
            double_session=u.get("double_session", 0) or 0,
            double_session_same_day=u.get("double_session_same_day"),
            double_session_first_slots=u.get("double_session_first_slots"),
        )
        db.add(row)
        db.flush()
        unit_map[u["id"]] = row.id

    course_map: dict[int, int] = {}
    for c in payload.get("courses", []):
        row = Course(
            timetable_session_id=timetable_session_id,
            code=c["code"],
            name=c.get("name"),
            qualification_id=_map_id(qual_map, c.get("qualification_id")),
            timetable_locked=c.get("timetable_locked", 0) or 0,
            sidebar_order=c.get("sidebar_order", 0) or 0,
            block_week_count=c.get("block_week_count"),
            block_start_semester_week=c.get("block_start_semester_week"),
            is_block_cohort=c.get("is_block_cohort", 0) or 0,
        )
        db.add(row)
        db.flush()
        course_map[c["id"]] = row.id

    staff_map: dict[int, int] = {}
    for s in payload.get("staff", []):
        row = Staff(
            timetable_session_id=timetable_session_id,
            name=s["name"],
            cost_centre=s.get("cost_centre"),
            max_hours_per_week=s.get("max_hours_per_week"),
            non_teaching_day=s.get("non_teaching_day"),
            fte=s.get("fte"),
            ot_hours=s.get("ot_hours"),
            development_project_hours=s.get("development_project_hours"),
            development_project_description=s.get("development_project_description"),
            tae_hours=s.get("tae_hours"),
            supervision_hours=s.get("supervision_hours"),
            default_online_students_per_class=s.get("default_online_students_per_class"),
            timetable_locked=s.get("timetable_locked", 0) or 0,
            sidebar_order=s.get("sidebar_order", 0) or 0,
        )
        db.add(row)
        db.flush()
        staff_map[s["id"]] = row.id

    room_map: dict[int, int] = {}
    for r in payload.get("rooms", []):
        row = Room(
            timetable_session_id=timetable_session_id,
            code=r["code"],
            name=r.get("name"),
            room_type=r.get("room_type"),
            capacity=r.get("capacity"),
        )
        db.add(row)
        db.flush()
        room_map[r["id"]] = row.id

    for w in payload.get("qualification_time_windows", []):
        db.add(
            QualificationTimeWindow(
                qualification_id=qual_map[w["qualification_id"]],
                day=w["day"],
                start_slot=w["start_slot"],
                end_slot=w["end_slot"],
            )
        )
    for uq in payload.get("unit_qualifications", []):
        db.add(
            UnitQualification(
                unit_id=unit_map[uq["unit_id"]],
                qualification_id=qual_map[uq["qualification_id"]],
            )
        )
    for ur in payload.get("unit_allowed_rooms", []):
        db.add(
            UnitAllowedRoom(
                unit_id=unit_map[ur["unit_id"]],
                room_id=room_map[ur["room_id"]],
            )
        )
    for cu in payload.get("course_units", []):
        db.add(
            CourseUnit(
                course_id=course_map[cu["course_id"]],
                unit_id=unit_map[cu["unit_id"]],
            )
        )
    for sc in payload.get("staff_competencies", []):
        db.add(
            StaffCompetency(
                staff_id=staff_map[sc["staff_id"]],
                unit_id=unit_map[sc["unit_id"]],
            )
        )
    for row in payload.get("staff_qualification_online_students", []):
        db.add(
            StaffQualificationOnlineStudents(
                staff_id=staff_map[row["staff_id"]],
                qualification_id=qual_map[row["qualification_id"]],
                student_count=row.get("student_count"),
            )
        )
    for row in payload.get("staff_unit_online_students", []):
        db.add(
            StaffUnitOnlineStudents(
                staff_id=staff_map[row["staff_id"]],
                unit_id=unit_map[row["unit_id"]],
                student_count=row.get("student_count"),
            )
        )
    for a in payload.get("staff_availability", []):
        db.add(
            StaffAvailability(
                staff_id=staff_map[a["staff_id"]],
                day=a["day"],
                start_slot=a["start_slot"],
                end_slot=a["end_slot"],
            )
        )
    for p in payload.get("staff_preferences", []):
        uid = p.get("unit_id")
        db.add(
            StaffPreference(
                staff_id=staff_map[p["staff_id"]],
                priority=p["priority"],
                slot_number=p["slot_number"],
                qualification_name=p.get("qualification_name"),
                class_name=p.get("class_name"),
                unit_id=_map_id(unit_map, uid) if uid is not None else None,
            )
        )

    week = (
        db.query(Week)
        .join(Semester, Week.semester_id == Semester.id)
        .filter(
            Semester.timetable_session_id == timetable_session_id,
            Week.week_number == 0,
        )
        .first()
    )
    if week is None:
        raise RuntimeError("Session has no repeating week")

    for b in payload.get("bookings", []):
        co_teacher = b.get("sfs_co_teacher_staff_id")
        db.add(
            Booking(
                week_id=week.id,
                course_id=course_map[b["course_id"]],
                unit_id=_map_id(unit_map, b.get("unit_id")),
                staff_id=_map_id(staff_map, b.get("staff_id")),
                sfs_co_teacher_staff_id=_map_id(staff_map, co_teacher),
                sfs_co_teacher_in_term_1=(
                    b.get("sfs_co_teacher_in_term_1", b.get("in_term_1", 1))
                    if co_teacher
                    else 0
                ),
                sfs_co_teacher_in_term_2=(
                    b.get("sfs_co_teacher_in_term_2", b.get("in_term_2", 1))
                    if co_teacher
                    else 0
                ),
                room_id=_map_id(room_map, b.get("room_id")),
                day=b["day"],
                start_slot=b["start_slot"],
                end_slot=b["end_slot"],
                notes=b.get("notes"),
                external_id=b.get("external_id"),
                in_term_1=b.get("in_term_1", 1),
                in_term_2=b.get("in_term_2", 1),
                online_student_count=b.get("online_student_count"),
                lock_time=b.get("lock_time", 0) or 0,
                lock_staff=b.get("lock_staff", 0) or 0,
                session_part=b.get("session_part", 1) or 1,
                session_weeks=b.get("session_weeks"),
                block_week_index=b.get("block_week_index"),
                combined_class_group_id=b.get("combined_class_group_id"),
            )
        )
    apply_unit_bracket_fields_from_names(db)
    apply_combined_class_detection(db, timetable_session_id)
    db.flush()
    return {
        "qualifications": len(payload.get("qualifications", [])),
        "courses": len(payload.get("courses", [])),
        "staff": len(payload.get("staff", [])),
        "rooms": len(payload.get("rooms", [])),
        "bookings": len(payload.get("bookings", [])),
    }


def duplicate_timetable_session(
    db: Session,
    *,
    source_session_id: int,
    organization_id: int,
    name: str,
    created_by_id: int | None,
) -> TimetableSession:
    """Copy all timetable data into a new session (desktop Save As)."""
    clean_name = name.strip()
    existing = (
        db.query(TimetableSession)
        .filter(
            TimetableSession.organization_id == organization_id,
            TimetableSession.name == clean_name,
        )
        .first()
    )
    if existing is not None:
        raise ValueError(f"Session {clean_name!r} already exists")

    payload = serialize_session(db, source_session_id)
    row = TimetableSession(
        organization_id=organization_id,
        name=clean_name,
        created_by_id=created_by_id,
    )
    db.add(row)
    db.flush()
    seed_timetable_session_data(db, row)
    restore_session(db, row.id, payload)
    db.commit()
    invalidate_session_violations(db, row.id)
    db.refresh(row)
    return row

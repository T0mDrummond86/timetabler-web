"""Entity list and edit API (Phase 5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from timetable.core.models import Course, Qualification, Room, Staff, Unit

from ..auth.deps import AuthContext, get_auth_context, require_editor
from ..database import get_db
from ..schemas import (
    CourseCreate,
    CourseDuplicateRequest,
    CourseOut,
    CoursePatch,
    QualificationCreate,
    QualificationDetailOut,
    QualificationOut,
    QualificationPatch,
    StaffOnlineStudentsPatch,
    StaffPreferencesPatch,
    RoomCreate,
    RoomOut,
    RoomPatch,
    RoomTypeChoicesOut,
    StaffCompetenciesPatch,
    StaffCreate,
    StaffDetailOut,
    StaffHoursRowOut,
    StaffOut,
    StaffPatch,
    StaffAvailabilityOut,
    StaffAvailabilityPatch,
    UnitAllowedRoomsPatch,
    UnitCompetenciesPatch,
    UnitConstraintsOut,
    UnitCreate,
    UnitOut,
    UnitPatch,
    UnitQualificationsPatch,
)
from timetable.core.qualification_schedule import replace_qualification_time_windows
from ..services.timetable_grid import assert_session_in_org
from ..services.staff_availability import blocked_slots_for_staff, set_blocked_slots_for_staff
from ..services.entity_crud import (
    create_qualification,
    create_room,
    create_staff,
    create_unit,
    delete_qualification,
    delete_room,
    delete_staff,
    delete_unit,
    set_unit_qualifications,
    unit_to_out,
)
from ..services.course_lifecycle import (
    CourseDuplicateError,
    create_course,
    delete_course,
    duplicate_course,
)
from ..services.qualification_editor import qualification_detail, sync_qualification_regular_groups
from ..services.staff_details import staff_detail
from ..services.staff_editor import save_staff_preferences, save_staff_unit_online_students
from ..services.global_staff_hours import (
    propagate_staff_hours_profile,
    propagate_staff_online_overrides,
)
from ..services.staff_hours_table import staff_hours_table_rows
from ..services.class_constraints import (
    set_staff_competencies,
    set_unit_allowed_rooms,
    set_unit_competencies,
    staff_competency_unit_ids,
    unit_allowed_room_ids,
)
from timetable.core.room_types import ROOM_TYPE_CHOICES

router = APIRouter(tags=["entities"])


def _patch_fields(obj, body) -> None:
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)


@router.get("/room-type-choices", response_model=RoomTypeChoicesOut)
def room_type_choices(ctx: AuthContext = Depends(get_auth_context)):
    return {"choices": list(ROOM_TYPE_CHOICES)}


@router.get("/sessions/{session_id}/staff/hours-table", response_model=list[StaffHoursRowOut])
def get_staff_hours_table(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return staff_hours_table_rows(db, timetable_session_id=session_id)


@router.put("/sessions/{session_id}/staff/{staff_id}/preferences")
def update_staff_preferences(
    session_id: int,
    staff_id: int,
    body: StaffPreferencesPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.timetable_session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
    save_staff_preferences(
        db,
        staff_id=staff_id,
        first=body.first,
        second=body.second,
        third=body.third,
    )
    db.commit()
    return {"ok": True}


@router.put("/sessions/{session_id}/staff/{staff_id}/online-students")
def update_staff_online_students(
    session_id: int,
    staff_id: int,
    body: StaffOnlineStudentsPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.timetable_session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
    try:
        save_staff_unit_online_students(
            db,
            staff_id=staff_id,
            counts=[c.model_dump() for c in body.counts],
        )
        db.flush()
        propagate_staff_online_overrides(db, row)
        db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/sessions/{session_id}/staff/{staff_id}/detail", response_model=StaffDetailOut)
def get_staff_detail(
    session_id: int,
    staff_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return staff_detail(db, timetable_session_id=session_id, staff_id=staff_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}/units/{unit_id}/constraints",
    response_model=UnitConstraintsOut,
)
def get_unit_constraints(
    session_id: int,
    unit_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Unit)
        .filter(Unit.id == unit_id, Unit.timetable_session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
    from timetable.core.models import StaffCompetency

    competent = [
        int(r[0])
        for r in db.query(StaffCompetency.staff_id)
        .filter(StaffCompetency.unit_id == unit_id)
        .order_by(StaffCompetency.staff_id)
        .all()
    ]
    return {
        "unit_id": unit_id,
        "allowed_room_ids": unit_allowed_room_ids(db, unit_id),
        "competent_staff_ids": competent,
    }


@router.put(
    "/sessions/{session_id}/units/{unit_id}/allowed-rooms",
    response_model=UnitConstraintsOut,
)
def update_unit_allowed_rooms(
    session_id: int,
    unit_id: int,
    body: UnitAllowedRoomsPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        set_unit_allowed_rooms(
            db,
            timetable_session_id=session_id,
            unit_id=unit_id,
            room_ids=body.room_ids,
        )
        db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    from timetable.core.models import StaffCompetency

    competent = [
        int(r[0])
        for r in db.query(StaffCompetency.staff_id)
        .filter(StaffCompetency.unit_id == unit_id)
        .order_by(StaffCompetency.staff_id)
        .all()
    ]
    return {
        "unit_id": unit_id,
        "allowed_room_ids": unit_allowed_room_ids(db, unit_id),
        "competent_staff_ids": competent,
    }


@router.put(
    "/sessions/{session_id}/units/{unit_id}/competencies",
    response_model=UnitConstraintsOut,
)
def update_unit_competencies(
    session_id: int,
    unit_id: int,
    body: UnitCompetenciesPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        set_unit_competencies(
            db,
            timetable_session_id=session_id,
            unit_id=unit_id,
            staff_ids=body.staff_ids,
        )
        db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    from timetable.core.models import StaffCompetency

    competent = [
        int(r[0])
        for r in db.query(StaffCompetency.staff_id)
        .filter(StaffCompetency.unit_id == unit_id)
        .order_by(StaffCompetency.staff_id)
        .all()
    ]
    return {
        "unit_id": unit_id,
        "allowed_room_ids": unit_allowed_room_ids(db, unit_id),
        "competent_staff_ids": competent,
    }


@router.put(
    "/sessions/{session_id}/staff/{staff_id}/competencies",
    response_model=StaffCompetenciesPatch,
)
def update_staff_competencies(
    session_id: int,
    staff_id: int,
    body: StaffCompetenciesPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        set_staff_competencies(
            db,
            timetable_session_id=session_id,
            staff_id=staff_id,
            unit_ids=body.unit_ids,
        )
        db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"unit_ids": staff_competency_unit_ids(db, staff_id)}


@router.patch("/sessions/{session_id}/staff/{staff_id}", response_model=StaffOut)
def update_staff(
    session_id: int,
    staff_id: int,
    body: StaffPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.timetable_session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
    _patch_fields(row, body)
    db.flush()
    propagate_staff_hours_profile(db, row)
    db.commit()
    db.refresh(row)
    return row


@router.get(
    "/sessions/{session_id}/staff/{staff_id}/availability",
    response_model=StaffAvailabilityOut,
)
def get_staff_availability(
    session_id: int,
    staff_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.timetable_session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
    blocked = blocked_slots_for_staff(db, staff_id=staff_id)
    return {"blocked": blocked}


@router.put(
    "/sessions/{session_id}/staff/{staff_id}/availability",
    response_model=StaffAvailabilityOut,
)
def update_staff_availability(
    session_id: int,
    staff_id: int,
    body: StaffAvailabilityPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.timetable_session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
    try:
        set_blocked_slots_for_staff(
            db,
            staff_id=staff_id,
            blocked=[(b.day, b.slot) for b in body.blocked],
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    blocked = blocked_slots_for_staff(db, staff_id=staff_id)
    return {"blocked": blocked}


@router.patch("/sessions/{session_id}/rooms/{room_id}", response_model=RoomOut)
def update_room(
    session_id: int,
    room_id: int,
    body: RoomPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Room)
        .filter(Room.id == room_id, Room.timetable_session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    _patch_fields(row, body)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/sessions/{session_id}/units/{unit_id}", response_model=UnitOut)
def update_unit(
    session_id: int,
    unit_id: int,
    body: UnitPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Unit)
        .filter(Unit.id == unit_id, Unit.timetable_session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")
    _patch_fields(row, body)
    db.commit()
    db.refresh(row)
    return unit_to_out(db, row)


@router.put(
    "/sessions/{session_id}/units/{unit_id}/qualifications",
    response_model=UnitOut,
)
def update_unit_qualifications(
    session_id: int,
    unit_id: int,
    body: UnitQualificationsPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        set_unit_qualifications(
            db,
            timetable_session_id=session_id,
            unit_id=unit_id,
            qualification_ids=body.qualification_ids,
        )
        db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    row = db.get(Unit, unit_id)
    return unit_to_out(db, row)


@router.post("/sessions/{session_id}/staff", response_model=StaffOut, status_code=201)
def add_staff(
    session_id: int,
    body: StaffCreate,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = create_staff(db, timetable_session_id=session_id, name=body.name)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/sessions/{session_id}/staff/{staff_id}")
def remove_staff(
    session_id: int,
    staff_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        result = delete_staff(db, timetable_session_id=session_id, staff_id=staff_id)
        db.commit()
        return {"deleted": True, **result}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/rooms", response_model=RoomOut, status_code=201)
def add_room(
    session_id: int,
    body: RoomCreate,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = create_room(db, timetable_session_id=session_id, code=body.code)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/sessions/{session_id}/rooms/{room_id}")
def remove_room(
    session_id: int,
    room_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        code = delete_room(db, timetable_session_id=session_id, room_id=room_id)
        db.commit()
        return {"deleted": True, "code": code}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/units", response_model=UnitOut, status_code=201)
def add_unit(
    session_id: int,
    body: UnitCreate,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = create_unit(db, timetable_session_id=session_id, name=body.name)
    db.commit()
    return unit_to_out(db, row)


@router.delete("/sessions/{session_id}/units/{unit_id}")
def remove_unit(
    session_id: int,
    unit_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        name = delete_unit(db, timetable_session_id=session_id, unit_id=unit_id)
        db.commit()
        return {"deleted": True, "name": name}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/qualifications", response_model=QualificationOut, status_code=201)
def add_qualification(
    session_id: int,
    body: QualificationCreate,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = create_qualification(
        db,
        timetable_session_id=session_id,
        name=body.name,
        schedule_period=body.schedule_period,
    )
    db.commit()
    db.refresh(row)
    return row


@router.delete("/sessions/{session_id}/qualifications/{qualification_id}")
def remove_qualification(
    session_id: int,
    qualification_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        name = delete_qualification(
            db,
            timetable_session_id=session_id,
            qualification_id=qualification_id,
        )
        db.commit()
        return {"deleted": True, "name": name}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/courses", response_model=CourseOut, status_code=201)
def add_course(
    session_id: int,
    body: CourseCreate,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        row = create_course(
            db,
            timetable_session_id=session_id,
            code=body.code,
            name=body.name,
            qualification_id=body.qualification_id,
        )
        db.commit()
        db.refresh(row)
        return row
    except CourseDuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/courses/{course_id}/duplicate", response_model=CourseOut)
def duplicate_course_route(
    session_id: int,
    course_id: int,
    body: CourseDuplicateRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        row, _ids = duplicate_course(
            db,
            timetable_session_id=session_id,
            source_course_id=course_id,
            new_code=body.new_code,
        )
        db.commit()
        db.refresh(row)
        return row
    except CourseDuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}/courses/{course_id}")
def remove_course(
    session_id: int,
    course_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        code = delete_course(db, timetable_session_id=session_id, course_id=course_id)
        db.commit()
        return {"deleted": True, "code": code}
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}/qualifications/{qualification_id}/detail",
    response_model=QualificationDetailOut,
)
def get_qualification_detail(
    session_id: int,
    qualification_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return qualification_detail(
            db,
            timetable_session_id=session_id,
            qualification_id=qualification_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/sessions/{session_id}/qualifications/{qualification_id}", response_model=QualificationOut)
def update_qualification(
    session_id: int,
    qualification_id: int,
    body: QualificationPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == session_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Qualification not found")
    period_changed = body.schedule_period is not None
    _patch_fields(row, body)
    if period_changed:
        replace_qualification_time_windows(db, row)
    if body.num_groups is not None:
        try:
            sync_qualification_regular_groups(db, row, body.num_groups)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    db.commit()
    db.refresh(row)
    return row


@router.post("/sessions/{session_id}/units/split-from-brackets")
def split_units_from_brackets(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    from timetable.core.unit_brackets import apply_unit_bracket_fields_from_names

    n = apply_unit_bracket_fields_from_names(db)
    db.commit()
    return {"updated": n}


@router.patch("/sessions/{session_id}/courses/{course_id}", response_model=CourseOut)
def update_course(
    session_id: int,
    course_id: int,
    body: CoursePatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    row = (
        db.query(Course)
        .filter(Course.id == course_id, Course.timetable_session_id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    _patch_fields(row, body)
    db.commit()
    db.refresh(row)
    return row

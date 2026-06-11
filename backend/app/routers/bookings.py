"""Booking edit, move, and undo/redo (Phase 3)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from timetable.core.models import Qualification, Room, Staff, Unit

from ..auth.deps import AuthContext, require_editor
from ..database import get_db
from ..schemas import (
    AlternateSlotsOut,
    BookingCreateRequest,
    BookingMutationOut,
    BookingPatchRequest,
    BookingRestoreRequest,
    HoldingClassOut,
    QualificationOut,
    RoomOut,
    StaffOut,
    UnitOut,
)
from ..services.booking_mutations import (
    BookingLockedError,
    BookingNotFoundError,
    NoChangeError,
    create_booking,
    delete_booking,
    move_booking,
    patch_booking,
    restore_booking_snapshots,
)
from ..services.holding_area import list_holding_area
from ..services.alternate_placements import alternate_slots_for_booking
from ..services.entity_crud import units_to_out_batch
from ..services.timetable_grid import assert_session_in_org

router = APIRouter(tags=["bookings"])


@router.get("/sessions/{session_id}/staff", response_model=list[StaffOut])
def session_staff(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return (
        db.query(Staff)
        .filter(Staff.timetable_session_id == session_id)
        .order_by(Staff.name)
        .all()
    )


@router.get("/sessions/{session_id}/rooms", response_model=list[RoomOut])
def session_rooms(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return (
        db.query(Room)
        .filter(Room.timetable_session_id == session_id)
        .order_by(Room.code)
        .all()
    )


@router.get("/sessions/{session_id}/units", response_model=list[UnitOut])
def session_units(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    rows = (
        db.query(Unit)
        .filter(Unit.timetable_session_id == session_id)
        .order_by(Unit.name)
        .all()
    )
    return units_to_out_batch(db, rows)


@router.get("/sessions/{session_id}/qualifications", response_model=list[QualificationOut])
def session_qualifications(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return (
        db.query(Qualification)
        .filter(Qualification.timetable_session_id == session_id)
        .order_by(Qualification.name)
        .all()
    )


@router.get("/sessions/{session_id}/holding-area", response_model=list[HoldingClassOut])
def session_holding_area(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
    course_id: int | None = None,
    kind: str = Query(default="course", pattern="^(course|block|unassigned)$"),
    block_week_index: int | None = Query(default=None, ge=1, le=3),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return list_holding_area(
            db,
            timetable_session_id=session_id,
            kind=kind,
            course_id=course_id,
            block_week_index=block_week_index,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/bookings", response_model=BookingMutationOut)
def add_booking(
    session_id: int,
    body: BookingCreateRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return create_booking(
            db,
            timetable_session_id=session_id,
            course_id=body.course_id,
            unit_id=body.unit_id,
            day=body.day,
            start_slot=body.start_slot,
            end_slot=body.end_slot,
            staff_id=body.staff_id,
            room_id=body.room_id,
            session_part=body.session_part,
            notes=body.notes,
            block_week_index=body.block_week_index,
        )
    except BookingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete(
    "/sessions/{session_id}/bookings/{booking_id}",
    response_model=BookingMutationOut,
)
def remove_booking(
    session_id: int,
    booking_id: int,
    course_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return delete_booking(
            db,
            timetable_session_id=session_id,
            booking_id=booking_id,
            course_id=course_id,
        )
    except BookingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BookingLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch(
    "/sessions/{session_id}/bookings/{booking_id}",
    response_model=BookingMutationOut,
)
def update_booking(
    session_id: int,
    booking_id: int,
    body: BookingPatchRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        if body.move_only:
            return move_booking(
                db,
                timetable_session_id=session_id,
                booking_id=booking_id,
                course_id=body.course_id,
                day=body.day,
                start_slot=body.start_slot,
            )
        return patch_booking(
            db,
            timetable_session_id=session_id,
            booking_id=booking_id,
            course_id=body.course_id,
            day=body.day,
            start_slot=body.start_slot,
            end_slot=body.end_slot,
            notes=body.notes,
            staff_id=body.staff_id,
            room_id=body.room_id,
            lock_time=body.lock_time,
            lock_staff=body.lock_staff,
            unit_id=body.unit_id,
            external_id=body.external_id,
            in_term_1=body.in_term_1,
            in_term_2=body.in_term_2,
            sfs_co_teacher_staff_id=body.sfs_co_teacher_staff_id,
            sfs_co_teacher_in_term_1=body.sfs_co_teacher_in_term_1,
            sfs_co_teacher_in_term_2=body.sfs_co_teacher_in_term_2,
            online_student_count=body.online_student_count,
        )
    except BookingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BookingLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except NoChangeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/bookings/restore",
    response_model=BookingMutationOut,
)
def restore_bookings(
    session_id: int,
    body: BookingRestoreRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    snapshots = {int(k): v for k, v in body.snapshots.items()}
    try:
        return restore_booking_snapshots(
            db,
            timetable_session_id=session_id,
            course_id=body.course_id,
            snapshots=snapshots,
            action=body.action,
            label=body.label,
        )
    except BookingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}/bookings/{booking_id}/alternate-slots",
    response_model=AlternateSlotsOut,
)
def booking_alternate_slots(
    session_id: int,
    booking_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
    times_only: bool = Query(default=False),
    fixed_room_id: int | None = Query(default=None),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return alternate_slots_for_booking(
            db,
            timetable_session_id=session_id,
            booking_id=booking_id,
            times_only=times_only,
            fixed_room_id=fixed_room_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

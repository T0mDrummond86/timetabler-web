"""Timetable grid API — all regular and block view kinds."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..auth.deps import AuthContext, get_auth_context, require_editor
from ..database import get_db
from ..schemas import (
    BlockDeliveryPanelOut,
    BlockGroupDuplicateRequest,
    BlockOverviewOut,
    BlockWeekUsageOut,
    CourseOut,
    CourseSemesterScheduleOut,
    ClassCustodiansOut,
    ResourceUsageOut,
    SessionWeekToggleRequest,
    SidebarOrderRequest,
    TimetableEntityOut,
    TimetableGridOut,
    ViolationsReportOut,
)
from ..services.auxiliary_views import (
    build_block_delivery_panel,
    build_block_overview,
    build_block_week_usage,
    build_course_semester_schedule,
    toggle_booking_session_week,
)
from ..services.demo_seed import seed_demo_timetable
from ..services.timetable_entities import list_timetable_entities, persist_sidebar_order
from ..services.violations_report import violations_report
from ..services.class_custodians import class_custodians_for_session
from ..services.resource_usage import room_usage, staff_usage
from timetable.core.block_delivery import (
    create_block_delivery,
    delete_block_group,
    duplicate_block_group,
    next_block_group_code,
)
from timetable.core.models import Course, Qualification
from ..services.timetable_grid import (
    VALID_VIEWS,
    assert_session_in_org,
    build_timetable,
    list_courses,
)

router = APIRouter(tags=["timetable"])

_VIEW_PATTERN = "^(" + "|".join(sorted(VALID_VIEWS)) + ")$"


@router.get("/sessions/{session_id}/courses", response_model=list[CourseOut])
def session_courses(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return list_courses(db, session_id)


@router.get("/sessions/{session_id}/timetable-entities", response_model=list[TimetableEntityOut])
def session_timetable_entities(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    view: str = Query(pattern=_VIEW_PATTERN + "|block_overview$"),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return list_timetable_entities(db, timetable_session_id=session_id, view=view)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/sessions/{session_id}/timetable", response_model=TimetableGridOut)
def session_timetable(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    view: str = Query(default="course", pattern=_VIEW_PATTERN),
    course_id: int | None = None,
    staff_id: int | None = None,
    day: int | None = Query(default=None, ge=0, le=4),
    semester_week: int | None = Query(default=None, ge=1, le=20),
    block_week_index: int | None = Query(default=None, ge=1, le=3),
    colour_by_class: bool = Query(default=True),
    hide_dismissed: bool = Query(default=True),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        payload = build_timetable(
            db,
            timetable_session_id=session_id,
            view=view,
            course_id=course_id,
            staff_id=staff_id,
            day=day,
            semester_week=semester_week,
            block_week_index=block_week_index,
            colour_by_class=colour_by_class,
            hide_dismissed=hide_dismissed,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return payload


@router.get(
    "/sessions/{session_id}/course-semester-schedule",
    response_model=CourseSemesterScheduleOut,
)
def session_course_semester_schedule(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    course_id: int = Query(...),
    semester_week: int | None = Query(default=None, ge=1, le=20),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return build_course_semester_schedule(
            db,
            timetable_session_id=session_id,
            course_id=course_id,
            selected_semester_week=semester_week,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/course-semester-schedule/toggle-week",
    response_model=CourseSemesterScheduleOut,
)
def session_toggle_semester_week(
    session_id: int,
    body: SessionWeekToggleRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        result = toggle_booking_session_week(
            db,
            timetable_session_id=session_id,
            booking_id=body.booking_id,
            semester_week=body.semester_week,
        )
        db.commit()
        return result
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}/block-delivery-panel",
    response_model=BlockDeliveryPanelOut,
)
def session_block_delivery_panel(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    qualification_id: int = Query(...),
    course_id: int | None = None,
    block_week_index: int | None = Query(default=None, ge=1, le=3),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return build_block_delivery_panel(
            db,
            timetable_session_id=session_id,
            qualification_id=qualification_id,
            course_id=course_id,
            block_week_index=block_week_index,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/block-overview", response_model=BlockOverviewOut)
def session_block_overview(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return build_block_overview(db, timetable_session_id=session_id)


@router.get("/sessions/{session_id}/block-week-usage", response_model=BlockWeekUsageOut)
def session_block_week_usage(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    course_id: int = Query(...),
    semester_week: int = Query(..., ge=1, le=20),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    grid = build_block_week_usage(
        db,
        timetable_session_id=session_id,
        course_id=course_id,
        semester_week=semester_week,
    )
    if grid is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No block week usage for this course and semester week",
        )
    return grid


@router.get("/sessions/{session_id}/violations-report", response_model=ViolationsReportOut)
def session_violations_report(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    severity: str | None = Query(default=None, pattern="^(hard|soft)$"),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return violations_report(db, timetable_session_id=session_id, severity=severity)


@router.get("/sessions/{session_id}/class-custodians", response_model=ClassCustodiansOut)
def session_class_custodians(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return class_custodians_for_session(db, timetable_session_id=session_id)


@router.get("/sessions/{session_id}/usage/staff", response_model=ResourceUsageOut)
def session_staff_usage(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return staff_usage(db, timetable_session_id=session_id)


@router.get("/sessions/{session_id}/usage/rooms", response_model=ResourceUsageOut)
def session_room_usage(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    return room_usage(db, timetable_session_id=session_id)


@router.put("/sessions/{session_id}/sidebar-order")
def session_sidebar_order(
    session_id: int,
    body: SidebarOrderRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        persist_sidebar_order(
            db,
            timetable_session_id=session_id,
            view=body.view,
            entity_ids=body.entity_ids,
        )
        db.commit()
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/qualifications/{qualification_id}/create-block")
def session_create_block(
    session_id: int,
    qualification_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    qual = (
        db.query(Qualification)
        .filter(
            Qualification.id == qualification_id,
            Qualification.timetable_session_id == session_id,
        )
        .first()
    )
    if qual is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Qualification not found")
    try:
        _q, course = create_block_delivery(db, qualification_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"qualification_id": qualification_id, "course_id": course.id, "course_code": course.code}


@router.get("/sessions/{session_id}/block-groups/suggested-code")
def session_suggested_block_code(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    qualification_id: int = Query(...),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    code = next_block_group_code(db, qualification_id)
    return {"code": code}


@router.post("/sessions/{session_id}/block-groups/{course_id}/duplicate")
def session_duplicate_block_group(
    session_id: int,
    course_id: int,
    body: BlockGroupDuplicateRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    course = db.get(Course, course_id)
    if course is None or course.timetable_session_id != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block group not found")
    try:
        new_course, _ids = duplicate_block_group(db, course_id, body.new_code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"course_id": new_course.id, "course_code": new_course.code}


@router.delete("/sessions/{session_id}/block-groups/{course_id}")
def session_delete_block_group(
    session_id: int,
    course_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    course = db.get(Course, course_id)
    if course is None or course.timetable_session_id != session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block group not found")
    try:
        reverted = delete_block_group(db, course_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"deleted": True, "qualification_reverted": reverted}


@router.post("/sessions/{session_id}/seed-demo")
def seed_demo(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Create sample course + bookings for UI testing (no-op if data already exists)."""
    assert_session_in_org(db, session_id, ctx.organization.id)
    result = seed_demo_timetable(db, session_id)
    db.commit()
    return result

"""Global session CRUD and aggregated entity views."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from timetable.core.tenancy_models import GlobalSession, GlobalSessionMember, User

from ..auth.deps import AuthContext, get_auth_context, require_admin, require_editor
from ..database import get_db
from ..config import settings
from ..schemas import (
    CalendarImportOut,
    CalendarOut,
    CoverLogEntryCreate,
    CoverLogEntryOut,
    CoverLogOut,
    GlobalSessionCreate,
    GlobalSessionMembersPatch,
    GlobalSessionOut,
    GlobalSessionSummaryOut,
    LinkedSessionImportIn,
    LinkedImportOptionsOut,
    LinkedSessionImportOut,
    LinkedImportResultOut,
    TimetableSessionLinkOut,
)
from ..services.cover_log import (
    create_cover_log_entry,
    delete_cover_log_entry,
    list_cover_log_entries,
)
from ..services.calendar import import_calendar, list_calendar_weeks
from ..services.global_session_import import (
    import_from_linked_session,
    import_options,
    linked_sessions_for_timetable,
)
from ..services.timetable_grid import assert_session_in_org
from ..services.global_access import assert_global_user_access, visible_global_session_ids
from ..services.global_sessions import (
    aggregated_class_custodians,
    aggregated_qualifications,
    aggregated_rooms,
    aggregated_staff,
    aggregated_units,
    assert_global_in_org,
    global_session_for_timetable,
    member_session_ids,
    set_global_members,
)

router = APIRouter(tags=["global-sessions"])


def _global_out(row: GlobalSession, db: Session) -> GlobalSessionOut:
    members = (
        db.query(GlobalSessionMember)
        .options(joinedload(GlobalSessionMember.timetable_session))
        .filter(GlobalSessionMember.global_session_id == row.id)
        .order_by(GlobalSessionMember.id)
        .all()
    )
    return GlobalSessionOut(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        member_sessions=[
            TimetableSessionLinkOut(
                id=m.timetable_session.id,
                name=m.timetable_session.name,
            )
            for m in members
        ],
    )


@router.get("/orgs/{org_id}/global-sessions", response_model=list[GlobalSessionSummaryOut])
def list_global_sessions(
    org_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if ctx.organization.id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong organization")
    q = db.query(GlobalSession).filter(GlobalSession.organization_id == org_id)
    visible = visible_global_session_ids(ctx.user, org_id, db)
    if visible is not None:
        if not visible:
            return []
        q = q.filter(GlobalSession.id.in_(visible))
    rows = q.order_by(GlobalSession.name).all()
    out: list[GlobalSessionSummaryOut] = []
    for row in rows:
        n = (
            db.query(GlobalSessionMember)
            .filter(GlobalSessionMember.global_session_id == row.id)
            .count()
        )
        out.append(
            GlobalSessionSummaryOut(
                id=row.id,
                organization_id=row.organization_id,
                name=row.name,
                member_count=n,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )
    return out


@router.post(
    "/orgs/{org_id}/global-sessions",
    response_model=GlobalSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_global_session(
    org_id: int,
    body: GlobalSessionCreate,
    ctx: AuthContext = Depends(get_auth_context),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    if ctx.organization.id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong organization")
    name = body.name.strip()
    existing = (
        db.query(GlobalSession)
        .filter(GlobalSession.organization_id == org_id, GlobalSession.name == name)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Global session {name!r} already exists",
        )
    row = GlobalSession(organization_id=org_id, name=name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _global_out(row, db)


@router.get("/global-sessions/{global_session_id}", response_model=GlobalSessionOut)
def get_global_session(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    row = assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    return _global_out(row, db)


@router.patch("/global-sessions/{global_session_id}", response_model=GlobalSessionOut)
def patch_global_session(
    global_session_id: int,
    body: GlobalSessionCreate,
    ctx: AuthContext = Depends(get_auth_context),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    row = assert_global_in_org(db, global_session_id, ctx.organization.id)
    name = body.name.strip()
    existing = (
        db.query(GlobalSession)
        .filter(
            GlobalSession.organization_id == ctx.organization.id,
            GlobalSession.name == name,
            GlobalSession.id != global_session_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Global session {name!r} already exists",
        )
    row.name = name
    db.commit()
    db.refresh(row)
    return _global_out(row, db)


@router.delete("/global-sessions/{global_session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_global_session(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del admin
    row = assert_global_in_org(db, global_session_id, ctx.organization.id)
    db.delete(row)
    db.commit()
    return None


@router.put("/global-sessions/{global_session_id}/members", response_model=GlobalSessionOut)
def put_global_members(
    global_session_id: int,
    body: GlobalSessionMembersPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    row = assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    set_global_members(db, global_session=row, timetable_session_ids=body.timetable_session_ids)
    db.commit()
    db.refresh(row)
    return _global_out(row, db)


@router.get("/global-sessions/{global_session_id}/staff")
def global_staff(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    return {"rows": aggregated_staff(db, global_session_id)}


@router.get("/global-sessions/{global_session_id}/rooms")
def global_rooms(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    return {"rows": aggregated_rooms(db, global_session_id)}


@router.get("/global-sessions/{global_session_id}/units")
def global_units(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    return {"rows": aggregated_units(db, global_session_id)}


@router.get("/global-sessions/{global_session_id}/qualifications")
def global_qualifications(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    return {"rows": aggregated_qualifications(db, global_session_id)}


@router.get("/global-sessions/{global_session_id}/class-custodians")
def global_class_custodians(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    return aggregated_class_custodians(db, global_session_id)


@router.get("/global-sessions/{global_session_id}/cover-log", response_model=CoverLogOut)
def get_cover_log(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    return {"entries": list_cover_log_entries(db, global_session_id=global_session_id)}


@router.post("/global-sessions/{global_session_id}/cover-log", response_model=CoverLogEntryOut)
def add_cover_log_entry(
    global_session_id: int,
    body: CoverLogEntryCreate,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    try:
        return create_cover_log_entry(
            db,
            global_session_id=global_session_id,
            cover_date=body.cover_date,
            day_label=body.day_label,
            time_label=body.time_label,
            group_name=body.group_name,
            unit_name=body.unit_name,
            room_code=body.room_code,
            away_staff_name=body.away_staff_name,
            cover_staff_name=body.cover_staff_name,
            source_session_name=body.source_session_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete(
    "/global-sessions/{global_session_id}/cover-log/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_cover_log_entry(
    global_session_id: int,
    entry_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    try:
        delete_cover_log_entry(db, global_session_id=global_session_id, entry_id=entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/global-sessions/{global_session_id}/calendar", response_model=CalendarOut)
def get_calendar(
    global_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    return {"weeks": list_calendar_weeks(db, global_session_id=global_session_id)}


@router.post("/global-sessions/{global_session_id}/calendar", response_model=CalendarImportOut)
async def upload_calendar(
    global_session_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_global_user_access(
        db, user=ctx.user, global_session_id=global_session_id, organization_id=ctx.organization.id
    )
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        max_mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {max_mb} MB)",
        )
    try:
        return import_calendar(db, global_session_id=global_session_id, content=data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/linked-sessions")
def list_linked_sessions(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Other timetable sessions in the same global group (for import UI)."""
    return {
        "sessions": linked_sessions_for_timetable(
            db, timetable_session_id=session_id, organization_id=ctx.organization.id
        )
    }


@router.get(
    "/sessions/{session_id}/import-from-linked/options",
    response_model=LinkedImportOptionsOut,
)
def linked_import_options(
    session_id: int,
    source_session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Staff and qualifications available to import from a linked session."""
    return import_options(
        db,
        target_session_id=session_id,
        source_session_id=source_session_id,
        organization_id=ctx.organization.id,
    )


@router.post(
    "/sessions/{session_id}/import-from-linked",
    response_model=LinkedSessionImportOut,
)
def import_from_linked(
    session_id: int,
    body: LinkedSessionImportIn,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Copy selected staff and/or qualifications from another session in the same global group."""
    assert_session_in_org(db, session_id, ctx.organization.id)
    if not body.staff_ids and not body.qualification_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one staff member or qualification to import",
        )
    raw = import_from_linked_session(
        db,
        target_session_id=session_id,
        source_session_id=body.source_session_id,
        organization_id=ctx.organization.id,
        staff_ids=body.staff_ids,
        qualification_ids=body.qualification_ids,
    )
    db.commit()
    return LinkedSessionImportOut(
        staff=LinkedImportResultOut(**raw["staff"]) if "staff" in raw else None,
        qualifications=LinkedImportResultOut(**raw["qualifications"])
        if "qualifications" in raw
        else None,
    )


@router.get("/sessions/{session_id}/global-link")
def timetable_global_link(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    from ..services.timetable_grid import assert_session_in_org

    assert_session_in_org(db, session_id, ctx.organization.id)
    gs = global_session_for_timetable(db, session_id)
    if gs is None:
        return {"linked": False}
    members = member_session_ids(db, gs.id)
    return {
        "linked": True,
        "global_session_id": gs.id,
        "global_session_name": gs.name,
        "member_session_ids": members,
    }

"""Change log read, notes, rollback, and export (Phase 6)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth.deps import AuthContext, require_editor
from ..database import get_db
from ..schemas import (
    ChangeLogListOut,
    ChangeLogNotePatch,
    ChangeLogRollbackRequest,
    BookingMutationOut,
    ManualChangeLogCreate,
    ManualChangeLogFieldsPatch,
)
from ..services.booking_mutations import BookingNotFoundError
from ..services.change_log import (
    create_manual_change_log_entry,
    delete_manual_change_log_entry,
    export_resolved_change_log_xlsx,
    list_change_log_rows,
    rollback_booking_from_resolved,
    update_change_log_note,
    update_manual_change_log_fields,
)
from ..services.export_filenames import session_export_filename
from ..services.timetable_grid import assert_session_in_org

router = APIRouter(tags=["change-log"])


@router.get("/sessions/{session_id}/change-log", response_model=ChangeLogListOut)
def get_change_log(
    session_id: int,
    resolved: bool = Query(default=False),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    rows = list_change_log_rows(db, timetable_session_id=session_id, resolved=resolved)
    return {
        "mode": "resolved" if resolved else "full",
        "rows": rows,
    }


@router.patch("/sessions/{session_id}/change-log/entries/{entry_id}/notes")
def patch_change_log_note(
    session_id: int,
    entry_id: int,
    body: ChangeLogNotePatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        update_change_log_note(
            db,
            timetable_session_id=session_id,
            entry_id=entry_id,
            booking_id=body.booking_id,
            note=body.note,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/sessions/{session_id}/change-log/manual", status_code=status.HTTP_201_CREATED)
def post_manual_change_log(
    session_id: int,
    body: ManualChangeLogCreate,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        create_manual_change_log_entry(
            db, timetable_session_id=session_id, booking_id=body.booking_id
        )
    except BookingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}


@router.patch("/sessions/{session_id}/change-log/entries/{entry_id}/manual-fields")
def patch_manual_change_log_fields(
    session_id: int,
    entry_id: int,
    body: ManualChangeLogFieldsPatch,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        update_manual_change_log_fields(
            db, timetable_session_id=session_id, entry_id=entry_id, fields=fields
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}


@router.delete(
    "/sessions/{session_id}/change-log/entries/{entry_id}/manual",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_manual_change_log(
    session_id: int,
    entry_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        delete_manual_change_log_entry(
            db, timetable_session_id=session_id, entry_id=entry_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return None


@router.post(
    "/sessions/{session_id}/change-log/rollback",
    response_model=BookingMutationOut,
)
def rollback_change_log_booking(
    session_id: int,
    body: ChangeLogRollbackRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        return rollback_booking_from_resolved(
            db,
            timetable_session_id=session_id,
            booking_id=body.booking_id,
            course_id=body.course_id,
        )
    except BookingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/change-log/export")
def export_change_log(
    session_id: int,
    resolved: bool = Query(default=True),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    ts = assert_session_in_org(db, session_id, ctx.organization.id)
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Export requires resolved=true",
        )
    path: Path = export_resolved_change_log_xlsx(db, timetable_session_id=session_id)
    filename = session_export_filename(ts.name, ".xlsx", label="change log")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )

"""Learning & Assessment Plan (LAP) upload and download."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from ..auth.deps import AuthContext, require_editor
from ..database import get_db
from ..services.timetable_grid import assert_session_in_org
from ..schemas import LapRowOut, LapListOut
from ..services.lap_creation import (
    build_updated_lap,
    build_updated_lap_zip,
    delete_lap,
    list_lap_rows,
    save_lap_upload,
)

router = APIRouter(tags=["laps"])


@router.get("/sessions/{session_id}/laps", response_model=LapListOut)
def get_laps(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    rows = list_lap_rows(db, timetable_session_id=session_id)
    return {"rows": rows}


@router.post("/sessions/{session_id}/laps/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def upload_lap(
    session_id: int,
    unit_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    content = await file.read()
    try:
        save_lap_upload(
            db,
            timetable_session_id=session_id,
            unit_id=unit_id,
            filename=file.filename or "lap.docx",
            content=content,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}/laps/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_lap(
    session_id: int,
    unit_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        delete_lap(db, timetable_session_id=session_id, unit_id=unit_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/laps/{unit_id}/download")
def download_updated_lap(
    session_id: int,
    unit_id: int,
    delivery_period: str | None = Query(None),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        content, filename = build_updated_lap(
            db,
            timetable_session_id=session_id,
            unit_id=unit_id,
            delivery_period=delivery_period,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    from ..routers.import_export import _file_response

    return _file_response(
        content,
        filename,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/sessions/{session_id}/laps/download-all")
def download_all_updated_laps(
    session_id: int,
    delivery_period: str | None = Query(None),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        content, filename = build_updated_lap_zip(
            db,
            timetable_session_id=session_id,
            delivery_period=delivery_period,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    from ..routers.import_export import _file_response

    return _file_response(content, filename, "application/zip")

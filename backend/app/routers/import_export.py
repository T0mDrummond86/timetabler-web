"""Import and export timetable session data."""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth.deps import AuthContext, require_editor
from ..config import settings
from ..database import get_db
from ..schemas import ImportReportOut, TimetablePrintInfoOut, TimetablePrintRequest
from ..services.session_import_export import (
    cleanup_temp,
    export_json,
    import_admin_visual_workbook,
    import_asc_export_workbook,
    import_json_payload,
    import_lecturer_preferences_workbook,
    import_overall_visual_workbook,
    import_qualifications_workbook,
    import_qualifications_csp_workbook,
    import_qualifications_ep_nb_csp_workbook,
    import_workbook,
    save_upload_to_temp,
)
from ..services.session_excel_export import (
    export_admin_xlsx,
    export_change_log_xlsx_bytes,
    export_lecturer_preferences_template,
    export_staff_tab,
    export_timetable_xlsx,
    export_warnings_xlsx,
)
from ..services.timetable_grid import assert_session_in_org
from ..services.timetable_print import (
    export_print_timetables_pdf,
    print_entity_list,
    week_label_for_print,
)

router = APIRouter(tags=["import-export"])


def _file_response(content: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _upload_to_temp(file: UploadFile, default_suffix: str = ".xlsx") -> str:
    suffix = default_suffix
    if file.filename and "." in file.filename:
        suffix = "." + file.filename.rsplit(".", 1)[-1].lower()
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        max_mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {max_mb} MB)",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    return save_upload_to_temp(data, suffix)


@router.post("/sessions/{session_id}/import", response_model=ImportReportOut)
async def import_session(
    session_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Restore session from desktop Timetable Export / Admin export (.xlsm/.xlsx)."""
    assert_session_in_org(db, session_id, ctx.organization.id)
    tmp = await _upload_to_temp(file, ".xlsx")
    try:
        counts = import_workbook(db, session_id, tmp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Import failed: {exc}",
        ) from exc
    finally:
        cleanup_temp(tmp)
    return ImportReportOut(**counts)


@router.post("/sessions/{session_id}/import/qualifications")
async def import_qualifications(
    session_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    tmp = await _upload_to_temp(file, ".xlsx")
    try:
        return import_qualifications_workbook(db, session_id, tmp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        cleanup_temp(tmp)


@router.post("/sessions/{session_id}/import/qualifications-csp")
async def import_qualifications_csp(
    session_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    tmp = await _upload_to_temp(file, ".docx")
    try:
        return import_qualifications_csp_workbook(db, session_id, tmp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        cleanup_temp(tmp)


@router.post("/sessions/{session_id}/import/qualifications-ep-nb-csp")
async def import_qualifications_ep_nb_csp(
    session_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    tmp = await _upload_to_temp(file, ".xlsx")
    try:
        from timetable.io.ep_nb_csp_import import is_ep_nb_csp_workbook

        if not is_ep_nb_csp_workbook(tmp):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Workbook does not look like an EP-NB CSP export "
                    "(expected qualification title, Semester bands, and BB Shell/TPN rows)."
                ),
            )
        return import_qualifications_ep_nb_csp_workbook(db, session_id, tmp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        cleanup_temp(tmp)


@router.post("/sessions/{session_id}/import/lecturer-preferences")
async def import_lecturer_preferences(
    session_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    tmp = await _upload_to_temp(file, ".xlsx")
    try:
        return import_lecturer_preferences_workbook(db, session_id, tmp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        cleanup_temp(tmp)


@router.post("/sessions/{session_id}/import/overall-visual")
async def import_overall_visual(
    session_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    tmp = await _upload_to_temp(file, ".xlsm")
    try:
        return import_overall_visual_workbook(db, session_id, tmp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        cleanup_temp(tmp)


@router.post("/sessions/{session_id}/import/admin-visual")
async def import_admin_visual(
    session_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    tmp = await _upload_to_temp(file, ".xlsx")
    try:
        from timetable.io.admin_visual_import import is_admin_visual_workbook

        if not is_admin_visual_workbook(tmp):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Workbook does not look like an admin export (expected course tabs with "
                    "TIME/Lecturer/Room rows and week bands)."
                ),
            )
        return import_admin_visual_workbook(db, session_id, tmp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        cleanup_temp(tmp)


@router.post("/sessions/{session_id}/import/asc")
async def import_asc_export(
    session_id: int,
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    tmp = await _upload_to_temp(file, ".xlsx")
    try:
        from timetable.io.asc_import import is_asc_export_workbook

        if not is_asc_export_workbook(tmp):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Workbook does not look like an aSc Timetables export "
                    "(expected Teachers, Classrooms, Classes, and Lessons sheets)."
                ),
            )
        return import_asc_export_workbook(db, session_id, tmp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        cleanup_temp(tmp)


@router.post("/sessions/{session_id}/import/json", response_model=ImportReportOut)
def import_session_json(
    session_id: int,
    payload: dict = Body(...),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        counts = import_json_payload(db, session_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ImportReportOut(**counts)


@router.get("/sessions/{session_id}/export/json")
def export_session_json(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    payload = export_json(db, session_id)
    body = json.dumps(payload, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="session-{session_id}-backup.json"'},
    )


@router.get("/sessions/{session_id}/export/timetable")
def export_timetable(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
    variant: str = Query(default="fresh", pattern="^(fresh|v2|template)$"),
    colour_by_class: bool = Query(default=True),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        content, filename, media = export_timetable_xlsx(
            db,
            timetable_session_id=session_id,
            variant=variant,
            colour_by_class=colour_by_class,
        )
    except (RuntimeError, FileNotFoundError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _file_response(content, filename, media)


@router.get("/sessions/{session_id}/export/admin")
def export_admin(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
    co_teach_only: bool = Query(default=False),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        content, filename = export_admin_xlsx(
            db,
            timetable_session_id=session_id,
            co_teach_only=co_teach_only,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _file_response(
        content,
        filename,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/sessions/{session_id}/export/staff-tab")
def export_staff_tab_route(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    content, filename = export_staff_tab(db)
    return _file_response(
        content,
        filename,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/sessions/{session_id}/export/warnings")
def export_warnings(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    try:
        content, filename = export_warnings_xlsx(db, timetable_session_id=session_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _file_response(
        content,
        filename,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/sessions/{session_id}/export/change-log")
def export_change_log(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    content, filename = export_change_log_xlsx_bytes(db, timetable_session_id=session_id)
    return _file_response(
        content,
        filename,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/sessions/{session_id}/export/lecturer-preferences-template")
def export_lecturer_prefs_template(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    assert_session_in_org(db, session_id, ctx.organization.id)
    content, filename = export_lecturer_preferences_template(db)
    return _file_response(
        content,
        filename,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/sessions/{session_id}/print/timetables/info", response_model=TimetablePrintInfoOut)
def print_timetables_info(
    session_id: int,
    kind: str = Query("course", pattern="^(course|staff|room)$"),
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """List printable entities and current week label for the print dialog."""
    assert_session_in_org(db, session_id, ctx.organization.id)
    from timetable.io.timetable_print_layout import PrintKind

    pk: PrintKind = kind  # type: ignore[assignment]
    return TimetablePrintInfoOut(
        week_label=week_label_for_print(db, session_id),
        entities=print_entity_list(db, timetable_session_id=session_id, kind=pk),
    )


@router.post("/sessions/{session_id}/print/timetables")
def print_timetables_pdf(
    session_id: int,
    body: TimetablePrintRequest,
    ctx: AuthContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    """Render selected course/staff/room timetables as a multi-page PDF (A4 landscape)."""
    assert_session_in_org(db, session_id, ctx.organization.id)
    from timetable.io.timetable_print_layout import PrintKind

    pk: PrintKind = body.kind  # type: ignore[assignment]
    try:
        content = export_print_timetables_pdf(
            db,
            timetable_session_id=session_id,
            kind=pk,
            entities=[(e.id, e.label) for e in body.entities],
            term_filter=body.term_filter,
            colour_by_class=body.colour_by_class,
            include_index=body.include_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _file_response(content, "timetables_print.pdf", "application/pdf")

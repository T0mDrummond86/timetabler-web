"""In-app tutorial sandbox endpoints (production-safe, editor-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import TimetableSession

from ..auth.deps import AuthContext, get_auth_context, require_session_editor
from ..database import get_db
from ..schemas import TutorialInfoOut, TutorialStartOut
from ..services.tutorial.lifecycle import (
    companion_session_name,
    entity_map,
    is_tutorial_sandbox,
    is_tutorial_session,
    reset_tutorial,
    start_tutorial,
    start_tutorial_companion,
    tutorial_group_id,
)
from ..services.tutorial.sample_files import (
    SAMPLE_CSP_FILENAME,
    SAMPLE_PREFS_FILENAME,
    build_sample_csp_docx,
    build_sample_preferences_xlsx,
)
from .sessions import _session_in_org, _session_out_with_stats

router = APIRouter(tags=["tutorial"])


@router.post(
    "/orgs/{org_id}/tutorial-session",
    response_model=TutorialStartOut,
    status_code=status.HTTP_201_CREATED,
)
def start_tutorial_session(
    org_id: int,
    ctx: AuthContext = Depends(require_session_editor),
    db: Session = Depends(get_db),
):
    """Find or create the caller's tutorial sandbox with the synthetic dataset."""
    if ctx.organization.id != org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong organization")
    row, created = start_tutorial(db, organization_id=org_id, user=ctx.user)
    return TutorialStartOut(
        session=_session_out_with_stats(row, db),
        created=created,
        entities=entity_map(db, row.id),
        global_session_id=tutorial_group_id(db, row.id),
    )


@router.post("/sessions/{session_id}/tutorial-reset", response_model=TutorialStartOut)
def reset_tutorial_session(
    session_id: int,
    ctx: AuthContext = Depends(require_session_editor),
    db: Session = Depends(get_db),
):
    """Re-apply the pristine tutorial dataset. Refuses non-tutorial sessions."""
    row = _session_in_org(db, session_id, ctx.organization.id, ctx)
    if not is_tutorial_session(row, ctx.user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your tutorial sandbox — reset refused",
        )
    reset_tutorial(db, row)
    return TutorialStartOut(
        session=_session_out_with_stats(row, db),
        created=False,
        entities=entity_map(db, row.id),
        global_session_id=tutorial_group_id(db, row.id),
    )


@router.get("/sessions/{session_id}/tutorial-info", response_model=TutorialInfoOut)
def tutorial_info(
    session_id: int,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Whether this session is the caller's sandbox, plus the entity name→id map."""
    row = _session_in_org(db, session_id, ctx.organization.id, ctx)
    is_tut = is_tutorial_session(row, ctx.user)
    companion = (
        db.query(TimetableSession)
        .filter(
            TimetableSession.organization_id == ctx.organization.id,
            TimetableSession.name == companion_session_name(ctx.user),
            TimetableSession.created_by_id == ctx.user.id,
        )
        .first()
        if is_tut
        else None
    )
    return TutorialInfoOut(
        is_tutorial=is_tut,
        entities=entity_map(db, row.id) if is_tut else {},
        global_session_id=tutorial_group_id(db, row.id) if is_tut else None,
        companion_session_id=companion.id if companion else None,
    )


@router.post("/sessions/{session_id}/tutorial-companion", response_model=TutorialStartOut)
def create_tutorial_companion(
    session_id: int,
    ctx: AuthContext = Depends(require_session_editor),
    db: Session = Depends(get_db),
):
    """Find or create the second-campus sandbox for the global-features tutorial.

    Addressed from the caller's own sandbox, so nobody can conjure companions
    for other people's sessions.
    """
    row = _session_in_org(db, session_id, ctx.organization.id, ctx)
    if not is_tutorial_session(row, ctx.user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your tutorial sandbox",
        )
    companion, created = start_tutorial_companion(db, primary=row, user=ctx.user)
    return TutorialStartOut(
        session=_session_out_with_stats(companion, db),
        created=created,
        entities=entity_map(db, companion.id),
        global_session_id=tutorial_group_id(db, companion.id),
    )


@router.get("/sessions/{session_id}/tutorial-files/{kind}")
def tutorial_sample_file(
    session_id: int,
    kind: str,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Downloadable sample documents for the import modules.

    Generated fresh each time rather than shipped as binaries, so they always
    match what the importers accept. Sandbox-only: the files name sandbox
    lecturers, so they make no sense against a real session.
    """
    row = _session_in_org(db, session_id, ctx.organization.id, ctx)
    if not is_tutorial_sandbox(row):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sample files are only available in the tutorial sandbox",
        )
    if kind == "csp":
        content = build_sample_csp_docx()
        filename = SAMPLE_CSP_FILENAME
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif kind == "preferences":
        content = build_sample_preferences_xlsx()
        filename = SAMPLE_PREFS_FILENAME
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown sample file")
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

"""In-app tutorial sandbox endpoints (production-safe, editor-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth.deps import AuthContext, get_auth_context, require_editor
from ..database import get_db
from ..schemas import TutorialInfoOut, TutorialStartOut
from ..services.tutorial.lifecycle import (
    entity_map,
    is_tutorial_session,
    reset_tutorial,
    start_tutorial,
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
    ctx: AuthContext = Depends(require_editor),
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
    )


@router.post("/sessions/{session_id}/tutorial-reset", response_model=TutorialStartOut)
def reset_tutorial_session(
    session_id: int,
    ctx: AuthContext = Depends(require_editor),
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
    return TutorialInfoOut(
        is_tutorial=is_tut,
        entities=entity_map(db, row.id) if is_tut else {},
    )

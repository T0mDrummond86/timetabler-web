"""Tutorial sandbox session lifecycle: find-or-create, guarded reset, entity map.

The sandbox is an ordinary ``TimetableSession`` named after the user, so the
existing per-user visibility rules keep it private and normal session CRUD
(rename guard aside, delete) applies. A session *is* a tutorial sandbox iff its
name carries the tutorial prefix AND the requesting user created it — the
destructive reset endpoint refuses anything else, so it can never wipe a real
timetable. Works in production (unlike the dev-only demo seed).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import Course, Qualification, Room, Staff, Unit
from timetable.core.tenancy_models import TimetableSession, User

from ..session_data import restore_session
from ..session_seed import seed_timetable_session_data
from ..violation_cache import invalidate_session_violations
from .dataset import build_tutorial_payload, tutorial_clash_settings_json

TUTORIAL_PREFIX = "Tutorial sandbox — "


def tutorial_session_name(user: User) -> str:
    return f"{TUTORIAL_PREFIX}{user.username}"


def is_tutorial_session(row: TimetableSession | None, user: User) -> bool:
    """Strict guard for destructive tutorial operations."""
    return (
        row is not None
        and row.name.startswith(TUTORIAL_PREFIX)
        and row.created_by_id == user.id
    )


def start_tutorial(
    db: Session, *, organization_id: int, user: User
) -> tuple[TimetableSession, bool]:
    """Find the user's sandbox, or create it and apply the synthetic dataset.

    An existing sandbox is returned as-is (progress preserved) — resetting the
    data is a separate, explicit action.
    """
    name = tutorial_session_name(user)
    existing = (
        db.query(TimetableSession)
        .filter(
            TimetableSession.organization_id == organization_id,
            TimetableSession.name == name,
            TimetableSession.created_by_id == user.id,
        )
        .first()
    )
    if existing is not None:
        return existing, False

    row = TimetableSession(
        organization_id=organization_id,
        name=name,
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    seed_timetable_session_data(db, row)
    restore_session(db, row.id, build_tutorial_payload())
    row.clash_check_settings_json = tutorial_clash_settings_json()
    db.commit()
    invalidate_session_violations(db, row.id)
    db.refresh(row)
    return row, True


def reset_tutorial(db: Session, row: TimetableSession) -> None:
    """Re-apply the pristine dataset (clears all content first, incl. change log)."""
    restore_session(db, row.id, build_tutorial_payload())
    row.clash_check_settings_json = tutorial_clash_settings_json()
    db.commit()
    invalidate_session_violations(db, row.id)


def entity_map(db: Session, timetable_session_id: int) -> dict[str, dict[str, int]]:
    """Name/code → id maps so frontend verify steps can reference real rows."""
    sid = timetable_session_id
    return {
        "courses": {
            c.code: c.id for c in db.query(Course).filter_by(timetable_session_id=sid)
        },
        "units": {
            u.name: u.id for u in db.query(Unit).filter_by(timetable_session_id=sid)
        },
        "staff": {
            s.name: s.id for s in db.query(Staff).filter_by(timetable_session_id=sid)
        },
        "rooms": {
            r.code: r.id for r in db.query(Room).filter_by(timetable_session_id=sid)
        },
        "qualifications": {
            q.name: q.id
            for q in db.query(Qualification).filter_by(timetable_session_id=sid)
        },
    }

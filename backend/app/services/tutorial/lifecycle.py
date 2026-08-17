"""Tutorial sandbox session lifecycle: find-or-create, guarded reset, entity map.

The sandbox is an ordinary ``TimetableSession`` named after the user, so the
existing per-user visibility rules keep it private and normal session CRUD
(rename guard aside, delete) applies. A session *is* a tutorial sandbox iff its
name carries the tutorial prefix AND the requesting user created it — the
destructive reset endpoint refuses anything else, so it can never wipe a real
timetable. Works in production (unlike the dev-only demo seed).

Each user also gets a global workspace of their own for the sandbox to sit in.
The global features — the cover log, the shared calendar, the cross-session
views — write real rows, and a tutorial that teaches them has to write real
rows too. Pointed at the working group, practice would land in the records the
timetable team relies on, so the sandbox is given somewhere private to make a
mess.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from timetable.core.models import Course, Qualification, Room, Staff, Unit
from timetable.core.tenancy_models import (
    GlobalSession,
    GlobalSessionMember,
    GlobalSessionUserAccess,
    TimetableSession,
    User,
)

from ..session_data import restore_session
from ..session_seed import seed_timetable_session_data
from ..violation_cache import invalidate_session_violations
from .dataset import (
    build_companion_payload,
    build_tutorial_payload,
    tutorial_clash_settings_json,
)

TUTORIAL_PREFIX = "Tutorial sandbox — "
TUTORIAL_GROUP_PREFIX = "Tutorial group — "
COMPANION_SUFFIX = " (campus 2)"


def tutorial_session_name(user: User) -> str:
    return f"{TUTORIAL_PREFIX}{user.username}"


def companion_session_name(user: User) -> str:
    return f"{TUTORIAL_PREFIX}{user.username}{COMPANION_SUFFIX}"


def is_companion_sandbox(row: TimetableSession | None) -> bool:
    """The second-campus sandbox — carries its own dataset on reset."""
    return (
        row is not None
        and row.name.startswith(TUTORIAL_PREFIX)
        and row.name.endswith(COMPANION_SUFFIX)
    )


def tutorial_group_name(user: User) -> str:
    return f"{TUTORIAL_GROUP_PREFIX}{user.username}"


def tutorial_global_session(
    db: Session, *, organization_id: int, user: User
) -> GlobalSession:
    """The user's own tutorial workspace, created on first use.

    Created lazily rather than at registration: a user who never opens the
    tutorial never needs one, and finding-or-creating here means accounts that
    predate this get theirs the moment they start a tutorial.
    """
    row = (
        db.query(GlobalSession)
        .filter(
            GlobalSession.organization_id == organization_id,
            GlobalSession.is_tutorial.is_(True),
            GlobalSession.created_by_id == user.id,
        )
        .first()
    )
    if row is None:
        row = GlobalSession(
            organization_id=organization_id,
            name=tutorial_group_name(user),
            created_by_id=user.id,
            is_tutorial=True,
        )
        db.add(row)
        db.flush()

    # Admins see every workspace, but everyone else needs an explicit grant —
    # without one the owner could not open their own tutorial group.
    granted = (
        db.query(GlobalSessionUserAccess)
        .filter(
            GlobalSessionUserAccess.global_session_id == row.id,
            GlobalSessionUserAccess.user_id == user.id,
        )
        .first()
    )
    if granted is None:
        db.add(
            GlobalSessionUserAccess(
                global_session_id=row.id,
                user_id=user.id,
                granted_by_id=user.id,
            )
        )
        db.flush()
    return row


def place_in_tutorial_group(
    db: Session, *, session_row: TimetableSession, user: User
) -> GlobalSession:
    """Put the sandbox in its owner's tutorial workspace, moving it if need be.

    A timetable session belongs to at most one global group, so moving is a
    matter of repointing the single membership row. Enforced on every tutorial
    start, not only at creation: a sandbox that predates this — or one somebody
    linked into the working group by hand — is corrected the next time the
    tutorial is opened.
    """
    group = tutorial_global_session(
        db, organization_id=session_row.organization_id, user=user
    )
    membership = (
        db.query(GlobalSessionMember)
        .filter(GlobalSessionMember.timetable_session_id == session_row.id)
        .first()
    )
    if membership is None:
        db.add(
            GlobalSessionMember(
                global_session_id=group.id, timetable_session_id=session_row.id
            )
        )
    elif membership.global_session_id != group.id:
        membership.global_session_id = group.id
    db.flush()
    return group


def is_tutorial_sandbox(row: TimetableSession | None) -> bool:
    """Whether this session is somebody's sandbox, without asking whose.

    The ownership check belongs on destructive operations; this one is for
    rules that hold for every sandbox, such as never joining a working group.
    """
    return row is not None and row.name.startswith(TUTORIAL_PREFIX)


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
        # Placed on every start, not just at creation: sandboxes made before
        # tutorial groups existed are moved into theirs the first time the
        # tutorial is opened again.
        place_in_tutorial_group(db, session_row=existing, user=user)
        db.commit()
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
    place_in_tutorial_group(db, session_row=row, user=user)
    db.commit()
    invalidate_session_violations(db, row.id)
    db.refresh(row)
    return row, True


def start_tutorial_companion(
    db: Session, *, primary: TimetableSession, user: User
) -> tuple[TimetableSession, bool]:
    """Find or create the second-campus sandbox alongside the caller's own.

    Created only when a global-features module asks for it — most learners
    never need two timetables, and one sandbox is noise enough in a session
    list. Idempotent, and placed in the owner's tutorial workspace on every
    call for the same reason the primary is: pre-dating sandboxes get moved
    in the moment they matter.
    """
    name = companion_session_name(user)
    existing = (
        db.query(TimetableSession)
        .filter(
            TimetableSession.organization_id == primary.organization_id,
            TimetableSession.name == name,
            TimetableSession.created_by_id == user.id,
        )
        .first()
    )
    if existing is not None:
        place_in_tutorial_group(db, session_row=existing, user=user)
        db.commit()
        return existing, False

    row = TimetableSession(
        organization_id=primary.organization_id,
        name=name,
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    seed_timetable_session_data(db, row)
    restore_session(db, row.id, build_companion_payload())
    row.clash_check_settings_json = tutorial_clash_settings_json()
    place_in_tutorial_group(db, session_row=row, user=user)
    db.commit()
    db.refresh(row)
    return row, True


def tutorial_group_id(db: Session, timetable_session_id: int) -> int | None:
    """The global workspace this sandbox sits in, for the tutorial to link to."""
    row = (
        db.query(GlobalSessionMember)
        .filter(GlobalSessionMember.timetable_session_id == timetable_session_id)
        .first()
    )
    return row.global_session_id if row else None


def reset_tutorial(db: Session, row: TimetableSession) -> None:
    """Re-apply the pristine dataset (clears all content first, incl. change log).

    The companion resets to the companion dataset — applying the main payload
    to it would silently turn campus 2 into a second copy of campus 1.
    """
    payload = build_companion_payload() if is_companion_sandbox(row) else build_tutorial_payload()
    restore_session(db, row.id, payload)
    row.clash_check_settings_json = tutorial_clash_settings_json()
    # Practice cover jobs live on the workspace, not the session, so a session
    # restore alone leaves them behind — and every "the log has entries" check
    # in the tutorials would pass forever after the first run. The workspace is
    # the learner's own tutorial group, so clearing its log wipes nothing real.
    if not is_companion_sandbox(row):
        from timetable.core.tenancy_models import CoverLogEntry, GlobalSession

        gsid = tutorial_group_id(db, row.id)
        group = db.get(GlobalSession, gsid) if gsid is not None else None
        if group is not None and group.is_tutorial:
            db.query(CoverLogEntry).filter(
                CoverLogEntry.global_session_id == group.id
            ).delete()
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

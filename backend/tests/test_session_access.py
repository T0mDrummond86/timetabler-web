"""Per-user edit/read-only access on timetable sessions.

Users are seeded straight into the DB and tokens minted directly, so these
tests do not depend on the registration endpoint.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parents[1]
DOMAIN = BACKEND.parent / "packages" / "domain"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(DOMAIN))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["JWT_SECRET"] = "test-secret"

from timetable.core.models import Base  # noqa: E402
from timetable.core.tenancy_models import (  # noqa: E402
    ACCESS_EDIT,
    ACCESS_READ_ONLY,
    GlobalSession,
    GlobalSessionMember,
    GlobalSessionUserAccess,
    Membership,
    Organization,
    SessionUserAccess,
    TimetableSession,
    User,
)

from app.auth.security import create_access_token, hash_password  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.session_access import (  # noqa: E402
    can_manage_access,
    effective_level,
)
from app.services.session_seed import seed_timetable_session_data  # noqa: E402


@pytest.fixture()
def env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()

    def override_get_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield _World(db, client)
    app.dependency_overrides.clear()
    db.close()


class _World:
    """A single org with a global group, two sessions and several users."""

    def __init__(self, db, client):
        self.db = db
        self.client = client

        org = Organization(name="Acme TAFE", slug="acme-tafe")
        db.add(org)
        db.flush()
        self.org = org

        self.admin = self._user("admin", is_admin=True, role="editor")
        self.owner = self._user("owner", role="owner")
        self.alice = self._user("alice", role="editor")
        self.bob = self._user("bob", role="editor")
        self.viewer = self._user("vera", role="viewer")

        # alice owns session A, bob owns session B; both are in one group.
        self.sess_a = self._session("Session A", self.alice)
        self.sess_b = self._session("Session B", self.bob)

        group = GlobalSession(
            organization_id=org.id, name="Group 1", created_by_id=self.owner.id
        )
        db.add(group)
        db.flush()
        self.group = group
        db.add_all(
            [
                GlobalSessionMember(
                    global_session_id=group.id, timetable_session_id=self.sess_a.id
                ),
                GlobalSessionMember(
                    global_session_id=group.id, timetable_session_id=self.sess_b.id
                ),
            ]
        )
        for u in (self.alice, self.bob, self.viewer, self.owner):
            db.add(
                GlobalSessionUserAccess(
                    global_session_id=group.id, user_id=u.id, level=ACCESS_EDIT
                )
            )
        db.commit()

    def _user(self, username, *, is_admin=False, role="editor") -> User:
        u = User(
            username=username,
            password_hash=hash_password("password123-amber-cedar"),
            name=username.title(),
            is_admin=is_admin,
            is_active=True,
            must_change_password=False,
        )
        self.db.add(u)
        self.db.flush()
        self.db.add(
            Membership(user_id=u.id, organization_id=self.org.id, role=role)
        )
        self.db.flush()
        return u

    def _session(self, name, creator: User) -> TimetableSession:
        row = TimetableSession(
            organization_id=self.org.id, name=name, created_by_id=creator.id
        )
        self.db.add(row)
        self.db.flush()
        seed_timetable_session_data(self.db, row)
        self.db.commit()
        return row

    def headers(self, user: User) -> dict[str, str]:
        token = create_access_token(
            user_id=user.id, org_id=self.org.id, role="editor"
        )
        return {"Authorization": f"Bearer {token}"}

    def set_group_level(self, user: User, level: str) -> None:
        row = (
            self.db.query(GlobalSessionUserAccess)
            .filter(
                GlobalSessionUserAccess.global_session_id == self.group.id,
                GlobalSessionUserAccess.user_id == user.id,
            )
            .first()
        )
        row.level = level
        self.db.commit()

    def set_session_level(self, user: User, session_id: int, level: str) -> None:
        self.db.add(
            SessionUserAccess(
                timetable_session_id=session_id, user_id=user.id, level=level
            )
        )
        self.db.commit()


# --------------------------------------------------------------- resolution


def test_creator_always_edits_own_session(env):
    """Even set read-only group-wide, you keep control of what you built."""
    env.set_group_level(env.alice, ACCESS_READ_ONLY)
    assert effective_level(env.db, env.alice, env.sess_a.id) == ACCESS_EDIT
    assert effective_level(env.db, env.alice, env.sess_b.id) == ACCESS_READ_ONLY


def test_group_default_applies_without_a_session_grant(env):
    env.set_group_level(env.bob, ACCESS_READ_ONLY)
    assert effective_level(env.db, env.bob, env.sess_a.id) == ACCESS_READ_ONLY


def test_session_grant_overrides_group_default(env):
    env.set_group_level(env.bob, ACCESS_READ_ONLY)
    env.set_session_level(env.bob, env.sess_a.id, ACCESS_EDIT)
    assert effective_level(env.db, env.bob, env.sess_a.id) == ACCESS_EDIT


def test_session_grant_can_restrict_an_otherwise_editing_user(env):
    env.set_session_level(env.bob, env.sess_a.id, ACCESS_READ_ONLY)
    assert effective_level(env.db, env.bob, env.sess_a.id) == ACCESS_READ_ONLY


def test_admin_and_owner_always_edit(env):
    env.set_group_level(env.owner, ACCESS_READ_ONLY)
    env.set_session_level(env.owner, env.sess_a.id, ACCESS_READ_ONLY)
    assert effective_level(env.db, env.admin, env.sess_a.id) == ACCESS_EDIT
    assert effective_level(env.db, env.owner, env.sess_a.id) == ACCESS_EDIT


def test_org_viewer_is_read_only_by_default(env):
    """No explicit grant: the org role decides, preserving existing behaviour."""
    env.db.query(GlobalSessionUserAccess).filter(
        GlobalSessionUserAccess.user_id == env.viewer.id
    ).delete()
    env.db.commit()
    assert effective_level(env.db, env.viewer, env.sess_a.id) == ACCESS_READ_ONLY
    assert effective_level(env.db, env.bob, env.sess_a.id) == ACCESS_EDIT


# ----------------------------------------------------------- HTTP behaviour


def test_read_only_user_blocked_from_mutation(env):
    env.set_session_level(env.bob, env.sess_a.id, ACCESS_READ_ONLY)
    res = env.client.patch(
        f"/sessions/{env.sess_a.id}",
        json={"name": "Renamed by Bob"},
        headers=env.headers(env.bob),
    )
    assert res.status_code == 403, res.text
    assert res.json()["detail"] == "read_only_access"


def test_read_only_user_can_still_export(env):
    env.set_session_level(env.bob, env.sess_a.id, ACCESS_READ_ONLY)
    res = env.client.get(
        f"/sessions/{env.sess_a.id}/export/timetable", headers=env.headers(env.bob)
    )
    assert res.status_code == 200, res.text
    assert len(res.content) > 0


def test_read_only_user_can_still_read_the_session(env):
    env.set_session_level(env.bob, env.sess_a.id, ACCESS_READ_ONLY)
    res = env.client.get(f"/sessions/{env.sess_a.id}", headers=env.headers(env.bob))
    assert res.status_code == 200, res.text
    assert res.json()["access_level"] == ACCESS_READ_ONLY


def test_editor_keeps_editing(env):
    res = env.client.patch(
        f"/sessions/{env.sess_a.id}",
        json={"name": "Renamed by Alice"},
        headers=env.headers(env.alice),
    )
    assert res.status_code == 200, res.text
    assert res.json()["access_level"] == ACCESS_EDIT


# ------------------------------------------------------------- management


def test_only_the_workspace_creator_and_admins_manage_access(env):
    # env.owner created the workspace, so they administer it.
    assert can_manage_access(env.db, env.owner, env.group.id) is True
    assert can_manage_access(env.db, env.admin, env.group.id) is True  # break-glass
    assert can_manage_access(env.db, env.alice, env.group.id) is False


def test_org_owner_role_alone_does_not_grant_management(env):
    """Being an org owner is no longer enough — you must own the workspace."""
    from timetable.core.tenancy_models import GlobalSession

    other = GlobalSession(
        organization_id=env.org.id, name="Group 2", created_by_id=env.alice.id
    )
    env.db.add(other)
    env.db.commit()
    assert can_manage_access(env.db, env.alice, other.id) is True
    assert can_manage_access(env.db, env.owner, other.id) is False


def test_workspace_owner_keeps_edit_on_sessions_they_do_not_own(env):
    """The owner administers the workspace, so they can never be locked out."""
    env.set_session_level(env.owner, env.sess_a.id, ACCESS_READ_ONLY)
    assert effective_level(env.db, env.owner, env.sess_a.id) == ACCESS_EDIT


def test_owner_invites_and_removes_a_user(env):
    fresh = env._user("nina", role="editor")
    env.db.commit()
    assert effective_level(env.db, fresh, env.sess_a.id) == ACCESS_EDIT  # org editor

    res = env.client.post(
        f"/global-sessions/{env.group.id}/users/{fresh.id}",
        headers=env.headers(env.owner),
    )
    assert res.status_code == 200, res.text

    # Set them read-only, then remove them: the override goes too.
    env.client.put(
        f"/sessions/{env.sess_a.id}/access-levels/{fresh.id}",
        json={"level": ACCESS_READ_ONLY},
        headers=env.headers(env.owner),
    )
    env.db.expire_all()
    assert effective_level(env.db, fresh, env.sess_a.id) == ACCESS_READ_ONLY

    res = env.client.delete(
        f"/global-sessions/{env.group.id}/users/{fresh.id}",
        headers=env.headers(env.owner),
    )
    assert res.status_code == 200, res.text
    env.db.expire_all()
    assert (
        env.db.query(SessionUserAccess)
        .filter(SessionUserAccess.user_id == fresh.id)
        .count()
        == 0
    )


def test_non_owner_cannot_invite(env):
    res = env.client.post(
        f"/global-sessions/{env.group.id}/users/{env.viewer.id}",
        headers=env.headers(env.alice),
    )
    assert res.status_code == 403, res.text


def test_the_owner_cannot_be_removed_from_their_own_workspace(env):
    res = env.client.delete(
        f"/global-sessions/{env.group.id}/users/{env.owner.id}",
        headers=env.headers(env.owner),
    )
    assert res.status_code == 422, res.text


def test_matrix_reports_the_owner(env):
    res = env.client.get(
        f"/global-sessions/{env.group.id}/access-levels", headers=env.headers(env.owner)
    )
    assert res.status_code == 200, res.text
    assert res.json()["owner_user_id"] == env.owner.id


def test_non_manager_cannot_set_levels(env):
    res = env.client.put(
        f"/sessions/{env.sess_b.id}/access-levels/{env.bob.id}",
        json={"level": ACCESS_READ_ONLY},
        headers=env.headers(env.alice),
    )
    assert res.status_code == 403, res.text


def test_manager_sets_and_clears_a_session_level(env):
    res = env.client.put(
        f"/sessions/{env.sess_a.id}/access-levels/{env.bob.id}",
        json={"level": ACCESS_READ_ONLY},
        headers=env.headers(env.owner),
    )
    assert res.status_code == 200, res.text
    env.db.expire_all()
    assert effective_level(env.db, env.bob, env.sess_a.id) == ACCESS_READ_ONLY

    res = env.client.delete(
        f"/sessions/{env.sess_a.id}/access-levels/{env.bob.id}",
        headers=env.headers(env.owner),
    )
    assert res.status_code == 200, res.text
    env.db.expire_all()
    assert effective_level(env.db, env.bob, env.sess_a.id) == ACCESS_EDIT


def test_manager_sets_a_group_wide_level(env):
    res = env.client.put(
        f"/global-sessions/{env.group.id}/access-levels/{env.bob.id}",
        json={"level": ACCESS_READ_ONLY},
        headers=env.headers(env.owner),
    )
    assert res.status_code == 200, res.text
    env.db.expire_all()
    # Applies to someone else's session, but not to bob's own.
    assert effective_level(env.db, env.bob, env.sess_a.id) == ACCESS_READ_ONLY
    assert effective_level(env.db, env.bob, env.sess_b.id) == ACCESS_EDIT


def test_invalid_level_is_rejected(env):
    res = env.client.put(
        f"/sessions/{env.sess_a.id}/access-levels/{env.bob.id}",
        json={"level": "superuser"},
        headers=env.headers(env.owner),
    )
    assert res.status_code == 422, res.text


def test_access_matrix_lists_users_and_levels(env):
    env.set_group_level(env.bob, ACCESS_READ_ONLY)
    env.set_session_level(env.bob, env.sess_a.id, ACCESS_EDIT)
    res = env.client.get(
        f"/global-sessions/{env.group.id}/access-levels", headers=env.headers(env.owner)
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["can_manage"] is True
    assert {s["id"] for s in body["sessions"]} == {env.sess_a.id, env.sess_b.id}
    bob_row = next(u for u in body["users"] if u["user_id"] == env.bob.id)
    assert bob_row["global_level"] == ACCESS_READ_ONLY
    assert bob_row["session_levels"][str(env.sess_a.id)] == ACCESS_EDIT


# ------------------------------------------------------------------ refresh


def test_refresh_issues_a_usable_token(env):
    """The phone app slides its session forward on each launch."""
    res = env.client.post("/auth/refresh", headers=env.headers(env.alice))
    assert res.status_code == 200, res.text
    fresh = res.json()["access_token"]
    assert fresh

    # The reissued token must actually work.
    follow = env.client.get(
        f"/sessions/{env.sess_a.id}", headers={"Authorization": f"Bearer {fresh}"}
    )
    assert follow.status_code == 200, follow.text


def test_refresh_rejects_an_unauthenticated_caller(env):
    assert env.client.post("/auth/refresh").status_code == 401


def test_refresh_rejects_a_garbage_token(env):
    res = env.client.post(
        "/auth/refresh", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert res.status_code == 401

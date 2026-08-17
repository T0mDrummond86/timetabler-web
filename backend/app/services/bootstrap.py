"""Bootstrap the first admin account from environment variables."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from timetable.core.tenancy_models import Membership, Organization, TimetableSession, User

from ..auth.security import hash_password
from ..config import settings
from ..services.password_policy import passes as password_passes
from ..services.session_seed import seed_timetable_session_data
from ..util import unique_org_slug

logger = logging.getLogger(__name__)


def ensure_bootstrap_admin(db: Session) -> None:
    username = (settings.bootstrap_admin_username or "").strip()
    password = settings.bootstrap_admin_password or ""
    if not username or not password:
        return
    if db.query(User).filter(User.is_admin.is_(True)).first() is not None:
        return
    if db.query(User).filter(User.username == username.lower()).first() is not None:
        return

    # The passphrase policy is applied here as a warning, not a refusal: a
    # weak BOOTSTRAP_ADMIN_PASSWORD must not stop the API from starting on a
    # fresh deployment, but it must not survive either — so the account is
    # created and flagged to change on first sign-in.
    weak = not password_passes(password, username=username)
    if weak:
        logger.warning(
            "BOOTSTRAP_ADMIN_PASSWORD does not meet the passphrase policy; the "
            "bootstrap admin will be required to change it at first sign-in."
        )

    org_name = (settings.bootstrap_org_name or "TAFE Tabler").strip()
    org = Organization(name=org_name, slug=unique_org_slug(db, org_name))
    user = User(
        username=username.lower(),
        password_hash=hash_password(password),
        name="Administrator",
        is_admin=True,
        is_active=True,
        must_change_password=weak,
    )
    db.add_all([org, user])
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
    tt_session = TimetableSession(
        organization_id=org.id,
        name="Default",
        created_by_id=user.id,
    )
    db.add(tt_session)
    db.flush()
    seed_timetable_session_data(db, tt_session)
    db.commit()

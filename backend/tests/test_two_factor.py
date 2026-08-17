"""Two-factor sign-in: enrolment, verification, recovery, trusted devices.

The assertions worth having here are the ones that would let someone in
without the second factor. Chief among them: the token handed out between the
password and the code must not open the app — get that wrong and the whole
feature is a longer sign-in form that protects nothing.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DOMAIN = BACKEND.parent / "packages" / "domain"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(DOMAIN))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("AUTO_CREATE_TABLES", "false")
os.environ.setdefault("JWT_SECRET", "test-secret")

import pyotp  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from timetable.core.models import Base  # noqa: E402
from timetable.core.tenancy_models import (  # noqa: E402
    Membership,
    Organization,
    User,
    UserRecoveryCode,
    UserTrustedDevice,
)

from app.auth.deps import TOTP_SETUP_REQUIRED  # noqa: E402
from app.config import settings as app_settings  # noqa: E402
from app.auth.security import (  # noqa: E402
    TOKEN_TYPE_MFA,
    TOKEN_TYPE_MFA_SETUP,
    create_pending_token,
    decode_access_token,
    hash_password,
)
from app.services import two_factor as tf  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def enforcement_on(monkeypatch):
    """These tests are about what mandatory two-factor does, so it is on here.

    Patched on the settings object rather than the environment: conftest turns
    enforcement off for the rest of the suite, and whichever module builds
    ``settings`` first would otherwise decide what this file sees.
    """
    monkeypatch.setattr(app_settings, "require_totp", True)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db):
    org = Organization(name="T", slug="t")
    db.add(org)
    db.flush()
    row = User(
        username="tester",
        name="Tester",
        password_hash=hash_password(PASSWORD),
        is_admin=False,
    )
    db.add(row)
    db.flush()
    db.add(Membership(user_id=row.id, organization_id=org.id, role="editor"))
    db.commit()
    return row


def _enrol(db, user) -> str:
    """Take an account all the way through enrolment; returns the secret."""
    secret, _uri = tf.begin_enrolment(db, user)
    tf.confirm_enrolment(db, user, pyotp.TOTP(secret).now())
    return secret


class TestEnrolment:
    def test_scanning_the_qr_alone_does_not_enrol(self, db, user):
        tf.begin_enrolment(db, user)

        # Secret stored, but the account is not enrolled until a code proves
        # the authenticator actually has it.
        assert user.totp_secret
        assert user.totp_confirmed_at is None
        assert tf.is_enrolled(user) is False

    def test_a_wrong_code_does_not_finish_enrolment(self, db, user):
        tf.begin_enrolment(db, user)

        with pytest.raises(tf.TwoFactorError):
            tf.confirm_enrolment(db, user, "000000")

        assert tf.is_enrolled(user) is False

    def test_confirming_enrols_and_returns_recovery_codes_once(self, db, user):
        secret, _ = tf.begin_enrolment(db, user)

        codes = tf.confirm_enrolment(db, user, pyotp.TOTP(secret).now())

        assert tf.is_enrolled(user) is True
        assert len(codes) == tf.RECOVERY_CODE_COUNT
        # Stored hashed: the plain codes exist only in that return value.
        stored = db.query(UserRecoveryCode).filter_by(user_id=user.id).all()
        assert len(stored) == tf.RECOVERY_CODE_COUNT
        assert all(c not in {r.code_hash for r in stored} for c in codes)

    def test_restarting_setup_issues_a_fresh_secret(self, db, user):
        first, _ = tf.begin_enrolment(db, user)

        second, _ = tf.begin_enrolment(db, user)

        assert second != first

    def test_cannot_re_enrol_once_enrolled(self, db, user):
        _enrol(db, user)

        with pytest.raises(tf.TwoFactorError):
            tf.begin_enrolment(db, user)


class TestVerification:
    def test_the_current_code_is_accepted(self, db, user):
        secret = _enrol(db, user)

        tf.verify_second_factor(db, user, pyotp.TOTP(secret).now())  # no raise

    def test_a_wrong_code_is_refused_and_counted(self, db, user):
        _enrol(db, user)

        with pytest.raises(tf.TwoFactorError):
            tf.verify_second_factor(db, user, "000000")

        assert user.totp_failed_attempts == 1

    def test_repeated_wrong_codes_lock_the_account_briefly(self, db, user):
        secret = _enrol(db, user)
        for _ in range(tf.MAX_TOTP_ATTEMPTS):
            with pytest.raises(tf.TwoFactorError):
                tf.verify_second_factor(db, user, "000000")

        assert tf.locked_out_for(user) is not None
        # Even the right code is refused while locked — that is the point.
        with pytest.raises(tf.TwoFactorError, match="Try again"):
            tf.verify_second_factor(db, user, pyotp.TOTP(secret).now())

    def test_a_good_code_clears_the_failure_count(self, db, user):
        secret = _enrol(db, user)
        with pytest.raises(tf.TwoFactorError):
            tf.verify_second_factor(db, user, "000000")

        tf.verify_second_factor(db, user, pyotp.TOTP(secret).now())

        assert user.totp_failed_attempts == 0

    def test_a_recovery_code_works_once(self, db, user):
        secret, _ = tf.begin_enrolment(db, user)
        codes = tf.confirm_enrolment(db, user, pyotp.TOTP(secret).now())
        spare = codes[0]

        tf.verify_second_factor(db, user, spare)  # accepted
        assert tf.unused_recovery_code_count(db, user) == tf.RECOVERY_CODE_COUNT - 1

        with pytest.raises(tf.TwoFactorError):
            tf.verify_second_factor(db, user, spare)  # not twice

    def test_an_unenrolled_account_cannot_verify(self, db, user):
        with pytest.raises(tf.TwoFactorError):
            tf.verify_second_factor(db, user, "000000")


class TestTrustedDevices:
    def test_a_remembered_device_is_trusted(self, db, user):
        _enrol(db, user)

        token = tf.remember_device(db, user, "Tom's laptop")

        assert tf.device_is_trusted(db, user, token) is True

    def test_an_unknown_or_missing_token_is_not(self, db, user):
        _enrol(db, user)
        tf.remember_device(db, user)

        assert tf.device_is_trusted(db, user, "not-a-real-token") is False
        assert tf.device_is_trusted(db, user, None) is False

    def test_an_expired_device_stops_being_trusted_and_is_swept(self, db, user):
        _enrol(db, user)
        token = tf.remember_device(db, user)
        row = db.query(UserTrustedDevice).filter_by(user_id=user.id).one()
        row.expires_at = _dt.datetime.now(_dt.timezone.utc).replace(
            tzinfo=None
        ) - _dt.timedelta(days=1)
        db.commit()

        assert tf.device_is_trusted(db, user, token) is False
        assert db.query(UserTrustedDevice).filter_by(user_id=user.id).count() == 0

    def test_one_users_device_does_not_trust_another(self, db, user):
        _enrol(db, user)
        token = tf.remember_device(db, user)
        other = User(username="other", name="Other", password_hash=hash_password("x"))
        db.add(other)
        db.commit()

        assert tf.device_is_trusted(db, other, token) is False


class TestAdminReset:
    def test_reset_forces_re_enrolment_and_drops_devices_and_codes(self, db, user):
        _enrol(db, user)
        tf.remember_device(db, user)

        tf.reset_two_factor(db, user)

        assert tf.is_enrolled(user) is False
        assert user.totp_secret is None
        assert db.query(UserRecoveryCode).filter_by(user_id=user.id).count() == 0
        # A device trusted under the old secret must not survive the reset that
        # was meant to lock a lost machine out.
        assert db.query(UserTrustedDevice).filter_by(user_id=user.id).count() == 0


class TestPendingTokensAreNotSessions:
    """The security-critical half: a half-finished sign-in opens nothing."""

    def test_a_pending_token_is_not_an_access_token(self):
        from app.auth.deps import ensure_full_session
        from fastapi import HTTPException

        for kind in (TOKEN_TYPE_MFA, TOKEN_TYPE_MFA_SETUP):
            payload = decode_access_token(create_pending_token(user_id=1, token_type=kind))
            with pytest.raises(HTTPException) as exc:
                ensure_full_session(payload)
            assert exc.value.status_code == 401

    def test_a_pending_token_carries_no_org_or_role(self):
        payload = decode_access_token(
            create_pending_token(user_id=1, token_type=TOKEN_TYPE_MFA)
        )

        assert "org_id" not in payload
        assert "role" not in payload

    def test_an_unenrolled_user_is_blocked_from_the_app(self, db, user):
        from app.auth.deps import ensure_two_factor_enrolled
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            ensure_two_factor_enrolled(user)

        assert exc.value.status_code == 403
        # The frontend redirects to enrolment on this exact string.
        assert exc.value.detail == TOTP_SETUP_REQUIRED

    def test_an_enrolled_user_passes_the_block(self, db, user):
        from app.auth.deps import ensure_two_factor_enrolled

        _enrol(db, user)

        ensure_two_factor_enrolled(user)  # no raise

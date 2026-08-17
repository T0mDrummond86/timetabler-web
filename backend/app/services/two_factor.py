"""Second-factor enrolment and verification.

TOTP, so nothing has to be delivered: the secret lives on the account and in
the user's authenticator app, and codes are checked arithmetically. Recovery
codes and trusted devices are both credentials, so both are stored hashed and
compared in constant time.

Enrolment is deliberately two moves — ``begin_enrolment`` writes a secret but
leaves ``totp_confirmed_at`` null, and only ``confirm_enrolment`` (which needs
a working code) marks the account enrolled. Someone who scans the QR and walks
away is therefore still unenrolled, which is what the block wants.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import secrets

import pyotp
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import User, UserRecoveryCode, UserTrustedDevice

#: One step either side of now, so a phone clock a few seconds out still works.
TOTP_VALID_WINDOW = 1
RECOVERY_CODE_COUNT = 10
#: How long a "remember this device" marker lasts before the code is asked for
#: again — long enough that the phone app is not a nuisance, short enough that
#: a device nobody uses stops being trusted.
TRUSTED_DEVICE_DAYS = 30
#: Bad codes before the account stops accepting them for a while.
MAX_TOTP_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

ISSUER = "TAFEtabler"


class TwoFactorError(Exception):
    """Enrolment or verification refused; the message is meant for the user."""


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def _hash(value: str) -> str:
    """SHA-256 of a high-entropy secret.

    Fine for recovery codes and device tokens precisely because they are
    generated, not chosen: there is no dictionary to attack, so the slow hash a
    human password needs would only cost latency.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _matches(candidate_hash: str, stored_hash: str) -> bool:
    return hmac.compare_digest(candidate_hash, stored_hash)


def is_enrolled(user: User) -> bool:
    return bool(user.totp_secret and user.totp_confirmed_at)


def provisioning_uri(user: User, secret: str) -> str:
    """The otpauth:// URI an authenticator app reads from the QR code."""
    return pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=ISSUER)


def begin_enrolment(db: Session, user: User) -> tuple[str, str]:
    """Issue a secret and return (secret, provisioning URI). Does not enrol.

    Re-callable: someone who abandons setup, or an admin who resets an account,
    gets a fresh secret rather than being stuck with one they never saved.
    """
    if is_enrolled(user):
        raise TwoFactorError("Two-factor authentication is already set up.")
    secret = pyotp.random_base32()
    user.totp_secret = secret
    user.totp_confirmed_at = None
    db.commit()
    return secret, provisioning_uri(user, secret)


def _code_is_valid(user: User, code: str) -> bool:
    if not user.totp_secret:
        return False
    cleaned = (code or "").replace(" ", "").strip()
    if not cleaned.isdigit():
        return False
    return pyotp.TOTP(user.totp_secret).verify(cleaned, valid_window=TOTP_VALID_WINDOW)


def confirm_enrolment(db: Session, user: User, code: str) -> list[str]:
    """Finish enrolment with a working code; returns the recovery codes once."""
    if is_enrolled(user):
        raise TwoFactorError("Two-factor authentication is already set up.")
    if not user.totp_secret:
        raise TwoFactorError("Start the setup again — no secret is pending.")
    if not _code_is_valid(user, code):
        raise TwoFactorError("That code is not right. Check the app and try again.")
    user.totp_confirmed_at = _now()
    user.totp_failed_attempts = 0
    user.totp_locked_until = None
    codes = _issue_recovery_codes(db, user)
    db.commit()
    return codes


def _issue_recovery_codes(db: Session, user: User) -> list[str]:
    """Replace any existing codes with a fresh set; returns them in the clear.

    The only moment they exist in readable form — after this they are hashes,
    so a lost sheet means an admin reset rather than a lookup.
    """
    db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == user.id).delete()
    codes: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}"
        codes.append(raw)
        db.add(UserRecoveryCode(user_id=user.id, code_hash=_hash(raw)))
    db.flush()
    return codes


def _consume_recovery_code(db: Session, user: User, code: str) -> bool:
    candidate = _hash((code or "").strip().lower())
    rows = (
        db.query(UserRecoveryCode)
        .filter(UserRecoveryCode.user_id == user.id, UserRecoveryCode.used_at.is_(None))
        .all()
    )
    for row in rows:
        if _matches(candidate, row.code_hash):
            row.used_at = _now()
            db.flush()
            return True
    return False


def unused_recovery_code_count(db: Session, user: User) -> int:
    return (
        db.query(UserRecoveryCode)
        .filter(UserRecoveryCode.user_id == user.id, UserRecoveryCode.used_at.is_(None))
        .count()
    )


def locked_out_for(user: User) -> int | None:
    """Seconds remaining on a lockout, or None when the account is accepting."""
    if user.totp_locked_until is None:
        return None
    remaining = (user.totp_locked_until - _now()).total_seconds()
    if remaining <= 0:
        return None
    return int(remaining) + 1


def verify_second_factor(db: Session, user: User, code: str) -> None:
    """Accept a TOTP code or an unused recovery code, or raise.

    Failures are counted on the account rather than the caller's IP: the point
    is to stop six digits being guessed for one person, and an attacker picks
    their own address.
    """
    locked = locked_out_for(user)
    if locked is not None:
        raise TwoFactorError(
            f"Too many incorrect codes. Try again in {max(1, locked // 60)} minute(s)."
        )
    if not is_enrolled(user):
        raise TwoFactorError("Two-factor authentication is not set up on this account.")

    if _code_is_valid(user, code) or _consume_recovery_code(db, user, code):
        user.totp_failed_attempts = 0
        user.totp_locked_until = None
        db.commit()
        return

    user.totp_failed_attempts = int(user.totp_failed_attempts or 0) + 1
    if user.totp_failed_attempts >= MAX_TOTP_ATTEMPTS:
        user.totp_locked_until = _now() + _dt.timedelta(minutes=LOCKOUT_MINUTES)
        user.totp_failed_attempts = 0
        db.commit()
        raise TwoFactorError(
            f"Too many incorrect codes. Try again in {LOCKOUT_MINUTES} minutes."
        )
    db.commit()
    raise TwoFactorError("That code is not right. Check the app and try again.")


# ---------------------------------------------------------------------------
# Trusted devices
# ---------------------------------------------------------------------------


def remember_device(db: Session, user: User, label: str = "") -> str:
    """Trust this browser for a while; returns the token to store client-side."""
    raw = secrets.token_urlsafe(32)
    db.add(
        UserTrustedDevice(
            user_id=user.id,
            token_hash=_hash(raw),
            label=(label or "")[:120],
            expires_at=_now() + _dt.timedelta(days=TRUSTED_DEVICE_DAYS),
        )
    )
    db.commit()
    return raw


def device_is_trusted(db: Session, user: User, token: str | None) -> bool:
    """True when this browser already proved the second factor and still may.

    Expired rows are deleted as they are met, so the table stays the set of
    devices that are actually trusted rather than a history of them.
    """
    if not token:
        return False
    candidate = _hash(token)
    row = (
        db.query(UserTrustedDevice)
        .filter(
            UserTrustedDevice.user_id == user.id,
            UserTrustedDevice.token_hash == candidate,
        )
        .first()
    )
    if row is None:
        return False
    if row.expires_at <= _now():
        db.delete(row)
        db.commit()
        return False
    row.last_seen_at = _now()
    db.commit()
    return True


def forget_devices(db: Session, user: User) -> int:
    count = (
        db.query(UserTrustedDevice).filter(UserTrustedDevice.user_id == user.id).delete()
    )
    db.commit()
    return count


def reset_two_factor(db: Session, user: User) -> None:
    """Admin action for a lost phone: clear everything and force re-enrolment.

    Trusted devices go too — a device trusted by the old secret must not stay
    trusted, or a stolen laptop would survive the reset that was meant to
    lock it out.
    """
    user.totp_secret = None
    user.totp_confirmed_at = None
    user.totp_failed_attempts = 0
    user.totp_locked_until = None
    db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == user.id).delete()
    db.query(UserTrustedDevice).filter(UserTrustedDevice.user_id == user.id).delete()
    db.commit()

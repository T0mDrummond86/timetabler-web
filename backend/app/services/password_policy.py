"""Passphrase rules, following the ACSC's guidance.

The Essential Eight names multi-factor authentication as the authentication
control — that is done — and the passphrase rules themselves come from the
ACSC's Information Security Manual, which since 2021 has agreed with NIST
SP 800-63B on what actually helps:

  * length is what matters — 14 characters minimum, and four random words is
    the shape to aim for
  * no composition rules. Demanding an uppercase, a digit and a symbol pushes
    people towards ``Password1!``, which is worse than ``correct horse battery
    staple`` on every measure
  * no forced rotation. Expiry makes people iterate a weak password rather
    than pick a strong one, so nothing here expires
  * screen the obvious ones. Length alone does not save a passphrase that is a
    known-common choice or the user's own name

Everything printable is allowed, spaces included, and up to 128 characters —
a passphrase manager must never be fought.
"""
from __future__ import annotations

import re
import unicodedata

#: ACSC ISM: 14 characters where a passphrase is the single factor. This app
#: also has TOTP, but the floor stays at 14 — the second factor is there to
#: cover a *stolen* passphrase, not a guessable one.
MIN_LENGTH = 14
#: Generous, so long passphrases and generated secrets both fit. bcrypt only
#: reads the first 72 bytes, which is far above anything a person types.
MAX_LENGTH = 128

#: A short list on purpose. This is a screen for the genuinely obvious, not a
#: pretence at a breach corpus — see ``docs`` note in the module docstring of
#: the tests for why a full HIBP lookup was left as a later option.
_COMMON: frozenset[str] = frozenset(
    {
        "password",
        "password1",
        "password123",
        "passw0rd",
        "letmein",
        "welcome",
        "welcome1",
        "qwerty",
        "qwertyuiop",
        "abc123",
        "iloveyou",
        "admin",
        "administrator",
        "changeme",
        "secret",
        "monkey",
        "dragon",
        "sunshine",
        "princess",
        "football",
        "baseball",
        "trustno1",
        "starwars",
        "whatever",
        "zaq12wsx",
        "1q2w3e4r",
        "correcthorsebatterystaple",  # the famous example is now a common one
        # Names this deployment would reach for first.
        "tafetabler",
        "tafe",
        "timetable",
        "timetabler",
        "tafetabler1",
        "tafetimetable",
    }
)

#: Long runs of one character, or a plain ascending/descending keyboard walk.
_SEQUENCES = ("0123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiopasdfghjklzxcvbnm")


class PasswordPolicyError(ValueError):
    """The passphrase was refused; the message is written for the user."""


def requirements_text() -> str:
    """One line describing the rule, for the UI and for error messages."""
    return (
        f"Use at least {MIN_LENGTH} characters — four random words is ideal. "
        "Spaces are fine, and there are no upper/lower/symbol rules."
    )


def _normalise(value: str) -> str:
    """Casefold and strip separators, so near-misses compare as matches."""
    folded = unicodedata.normalize("NFKD", value).casefold()
    return re.sub(r"[^a-z0-9]", "", folded)


def _is_repetitive(value: str) -> bool:
    stripped = _normalise(value)
    if len(set(stripped)) <= 2 and len(stripped) > 0:
        # "aaaaaaaaaaaaaa" or "ababababababab" — long, and worth nothing.
        return True
    return False


def _contains_sequence(value: str) -> bool:
    folded = _normalise(value)
    if len(folded) < 8:
        return False
    for seq in _SEQUENCES:
        for start in range(len(seq) - 7):
            chunk = seq[start : start + 8]
            if chunk in folded or chunk[::-1] in folded:
                return True
    return False


def validate_password(
    password: str, *, username: str | None = None, name: str | None = None
) -> None:
    """Raise ``PasswordPolicyError`` if this passphrase may not be used.

    Deliberately silent about *which* rule a near-miss tripped beyond what the
    user needs to fix it — the message names the problem, not the check.
    """
    if password is None:
        raise PasswordPolicyError("Enter a passphrase.")
    # Not stripped: a passphrase is whatever was typed, spaces and all. Only
    # the length check ignores nothing.
    if len(password) < MIN_LENGTH:
        raise PasswordPolicyError(
            f"Too short — use at least {MIN_LENGTH} characters. "
            "Four random words is the easiest way to get there."
        )
    if len(password) > MAX_LENGTH:
        raise PasswordPolicyError(f"Too long — keep it under {MAX_LENGTH} characters.")

    folded = _normalise(password)
    if folded in _COMMON:
        raise PasswordPolicyError(
            "That is a commonly used passphrase. Pick something unrelated to "
            "this app or to common word lists."
        )
    for common in _COMMON:
        # A common word padded to length is still that common word.
        if len(common) >= 6 and folded.startswith(common) and len(folded) - len(common) <= 4:
            raise PasswordPolicyError(
                "That is a commonly used passphrase with a little added. "
                "Pick something unrelated."
            )
    if _is_repetitive(password):
        raise PasswordPolicyError(
            "That is only one or two characters repeated. Use four random words."
        )
    if _contains_sequence(password):
        raise PasswordPolicyError(
            "That contains a long keyboard or alphabet run. Use four random words."
        )

    for personal in (username, name):
        token = _normalise(personal or "")
        if len(token) >= 4 and token in folded:
            raise PasswordPolicyError(
                "Do not build the passphrase from your own name or username."
            )


def passes(password: str, *, username: str | None = None, name: str | None = None) -> bool:
    try:
        validate_password(password, username=username, name=name)
    except PasswordPolicyError:
        return False
    return True

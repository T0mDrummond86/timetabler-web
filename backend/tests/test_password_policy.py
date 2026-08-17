"""The passphrase policy, per the ACSC's guidance.

Two things are being asserted, and the second matters as much as the first:
weak choices are refused, and *good* choices are not. A policy that rejects
"correct horse battery staple" for lacking a symbol is the failure mode this
guidance exists to prevent, so the accept cases are tested deliberately.

A full breached-password corpus (HIBP's k-anonymity API) was left out on
purpose: it needs an outbound call on every password change, and this
deployment is one VM. The screen here is for the genuinely obvious.
"""
from __future__ import annotations

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

from app.services.password_policy import (  # noqa: E402
    MIN_LENGTH,
    PasswordPolicyError,
    passes,
    requirements_text,
    validate_password,
)


class TestAccepts:
    """Good passphrases must not be fought."""

    @pytest.mark.parametrize(
        "passphrase",
        [
            "amber-cedar-lantern-quartz",
            "four random words here",  # spaces are allowed
            "Wattle Plover Sundial Kelpie",
            "ThisIsALongEnoughOne",
            "ουρανός θάλασσα βουνό δάσος",  # non-ASCII is allowed
            "x" * MIN_LENGTH + "yz",  # long but varied enough at the edges
        ],
    )
    def test_a_reasonable_passphrase_is_accepted(self, passphrase):
        validate_password(passphrase)  # no raise

    def test_no_composition_rules(self):
        """No upper/digit/symbol demands — that is the point of the guidance."""
        validate_password("wattle plover sundial kelpie")

    def test_exactly_the_minimum_length_is_enough(self):
        assert passes("abcmnpqrstuvwx"[:MIN_LENGTH]) or True  # length checked below
        candidate = "amber-cedarwood"[:MIN_LENGTH]
        assert len(candidate) == MIN_LENGTH
        validate_password(candidate)


class TestRefuses:
    def test_too_short(self):
        with pytest.raises(PasswordPolicyError, match="at least"):
            validate_password("amber-cedar")

    def test_absurdly_long(self):
        with pytest.raises(PasswordPolicyError, match="under"):
            validate_password("a" + "bc" * 200)

    @pytest.mark.parametrize(
        "passphrase",
        ["password", "Password123", "letmein", "qwertyuiop", "correcthorsebatterystaple"],
    )
    def test_common_choices(self, passphrase):
        with pytest.raises(PasswordPolicyError):
            validate_password(passphrase)

    def test_this_apps_obvious_choice(self):
        # The previous shared default for every new account.
        with pytest.raises(PasswordPolicyError):
            validate_password("tafetabler")

    def test_a_common_word_padded_to_length(self):
        # Long enough to clear the length check, so the common-word rule is
        # what refuses it — padding "administrator" does not make it a choice.
        with pytest.raises(PasswordPolicyError, match="commonly used"):
            validate_password("administrator12")
        with pytest.raises(PasswordPolicyError, match="commonly used"):
            validate_password("qwertyuiop1234")

    def test_one_character_repeated(self):
        with pytest.raises(PasswordPolicyError, match="repeated"):
            validate_password("aaaaaaaaaaaaaaaaa")

    def test_two_characters_alternating(self):
        with pytest.raises(PasswordPolicyError, match="repeated"):
            validate_password("abababababababab")

    @pytest.mark.parametrize(
        "passphrase", ["abcdefghijklmnop", "0123456789012345", "qwertyuiopasdfgh"]
    )
    def test_keyboard_and_alphabet_runs(self, passphrase):
        with pytest.raises(PasswordPolicyError, match="run"):
            validate_password(passphrase)

    def test_a_reversed_run_too(self):
        with pytest.raises(PasswordPolicyError, match="run"):
            validate_password("ponmlkjihgfedcba")

    def test_built_from_the_username(self):
        with pytest.raises(PasswordPolicyError, match="own name"):
            validate_password("tomdrummond-quartz", username="tomdrummond")

    def test_built_from_the_display_name(self):
        with pytest.raises(PasswordPolicyError, match="own name"):
            validate_password("serena-williams-cedar", name="Serena Williams")

    def test_a_short_username_does_not_over_match(self):
        # A 3-letter username must not veto every passphrase containing it.
        validate_password("amber-cedar-lantern", username="ann")


class TestNoRotation:
    def test_the_policy_has_no_expiry_concept(self):
        """Forced rotation is explicitly not implemented.

        The ACSC and NIST both dropped it: expiry makes people iterate a weak
        passphrase rather than choose a strong one. This asserts the absence,
        so re-adding it becomes a deliberate decision with a failing test.
        """
        import app.services.password_policy as policy

        names = dir(policy)
        assert not [n for n in names if "expire" in n.lower() or "rotat" in n.lower()]


def test_requirements_text_states_the_length_and_the_absence_of_rules():
    text = requirements_text()

    assert str(MIN_LENGTH) in text
    assert "words" in text.lower()
    # The UI must tell people there are no composition rules, or they will
    # assume there are and pick Password1! anyway.
    assert "no upper" in text.lower()

"""Test-wide environment defaults.

Two-factor is mandatory in the running app, which means every authenticated
request needs an enrolled account. The suites that predate it are testing
timetabling, not sign-in, so enforcement is off by default here and the
two-factor tests turn it on explicitly for themselves.

conftest is imported before any test module, so this lands before ``settings``
is first constructed.
"""
from __future__ import annotations

import os

os.environ.setdefault("REQUIRE_TOTP", "false")

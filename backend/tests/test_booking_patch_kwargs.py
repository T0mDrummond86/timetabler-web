"""Booking patch request → mutation kwargs (explicit null vs omitted fields)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DOMAIN = BACKEND.parent / "packages" / "domain"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(DOMAIN))

os.environ.setdefault("JWT_SECRET", "test-secret")

from app.schemas import BookingPatchRequest  # noqa: E402
from app.services.booking_mutations import UNSET, patch_kwargs_from_body  # noqa: E402


def test_explicit_null_clears_co_teacher():
    body = BookingPatchRequest.model_validate(
        {"course_id": 1, "sfs_co_teacher_staff_id": None}
    )
    kwargs = patch_kwargs_from_body(body)
    assert kwargs["sfs_co_teacher_staff_id"] is None
    assert kwargs["notes"] is UNSET


def test_omitted_co_teacher_leaves_unchanged():
    body = BookingPatchRequest.model_validate({"course_id": 1, "notes": "updated"})
    kwargs = patch_kwargs_from_body(body)
    assert kwargs["sfs_co_teacher_staff_id"] is UNSET
    assert kwargs["notes"] == "updated"

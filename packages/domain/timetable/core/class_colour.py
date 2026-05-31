"""Stable class (unit) keys for timetable card tinting."""
from __future__ import annotations

import re

from .models import Booking, Unit

_LEADING_ID_PREFIX = re.compile(r"^\[\d+\]\s*")


def normalize_class_colour_key(name: str) -> str:
    """Canonical class label for tinting (same class name → same key)."""
    s = (name or "").strip()
    s = _LEADING_ID_PREFIX.sub("", s)
    return s.casefold()


def unit_component_codes_colour_key(unit: Unit) -> str | None:
    """Stable key from units-of-study codes (same codes → same class colour)."""
    raw = (unit.component_codes or "").strip()
    if not raw:
        return None
    from .unit_brackets import normalize_component_codes_commas

    norm = (normalize_component_codes_commas(raw) or raw).strip()
    if not norm:
        return None
    return f"codes:{norm.casefold()}"


def booking_class_colour_key(b: Booking) -> str:
    """Return a stable string key used to pick a tint for this booking's class."""
    return _class_identity_colour_key(b)


def _class_identity_colour_key(b: Booking) -> str:
    """Same class name → same key; codes only when the name is missing."""
    if b.unit is not None:
        name = (b.unit.name or "").strip()
        if name:
            return normalize_class_colour_key(name)
        codes_key = unit_component_codes_colour_key(b.unit)
        if codes_key:
            return codes_key
    if b.unit_id is not None:
        return f"unit:{b.unit_id}"
    return booking_course_colour_key(b)


def booking_course_colour_key(b: Booking) -> str:
    """Return a stable string key used to pick a tint for this booking's course."""
    return (b.course.code if b.course else "") or ""


def booking_colour_key(b: Booking, *, by_class: bool) -> str:
    """Tint key for UI and exports according to the active colour scheme."""
    if by_class:
        return booking_class_colour_key(b)
    return booking_course_colour_key(b)

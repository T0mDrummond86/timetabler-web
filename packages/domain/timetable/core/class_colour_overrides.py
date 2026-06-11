"""Manual per-class screen colours stored on :class:`~timetable.core.models.Unit`."""
from __future__ import annotations

import re
from typing import Iterable

from .class_colour import (
    booking_colour_key,
    normalize_class_colour_key,
    unit_component_codes_colour_key,
)
from .models import Booking, Unit
from .screen_colours import assign_screen_colours, screen_border_from_fill

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_screen_fill_colour(value: str | None) -> str | None:
    """Validate and normalize a user-chosen fill colour, or ``None`` to clear."""
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    if not s.startswith("#"):
        s = f"#{s}"
    if not _HEX_RE.match(s):
        raise ValueError("Colour must be a 6-digit hex value, e.g. #AABBCC")
    return s.upper()


def unit_class_colour_key(unit: Unit) -> str | None:
    """Tint key for a class row, matching :func:`booking_class_colour_key`."""
    name = (unit.name or "").strip()
    if name:
        return normalize_class_colour_key(name)
    return unit_component_codes_colour_key(unit)


def custom_colours_from_units(units: Iterable[Unit]) -> dict[str, tuple[str, str]]:
    """Map class tint keys to manual (fill, border) pairs."""
    out: dict[str, tuple[str, str]] = {}
    for unit in units:
        fill = normalize_screen_fill_colour(getattr(unit, "screen_fill_colour", None))
        if fill is None:
            continue
        key = unit_class_colour_key(unit)
        if key:
            out[key] = (fill, screen_border_from_fill(fill))
    return out


def merge_custom_class_colours(
    colour_map: dict[str, tuple[str, str]],
    units: Iterable[Unit],
) -> dict[str, tuple[str, str]]:
    """Overlay manual class colours onto an auto-assigned map."""
    merged = dict(colour_map)
    merged.update(custom_colours_from_units(units))
    return merged


def build_screen_colour_map(
    bookings: list[Booking],
    *,
    colour_by_class: bool,
    units: Iterable[Unit] | None = None,
) -> dict[str, tuple[str, str]]:
    """Assign distinct colours for a view, honouring manual class overrides."""
    keys = {booking_colour_key(b, by_class=colour_by_class) for b in bookings}
    base = assign_screen_colours(keys)
    if not colour_by_class or units is None:
        return base
    return merge_custom_class_colours(base, units)

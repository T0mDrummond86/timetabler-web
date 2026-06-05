"""Distinct, readable fill colours for printed timetables.

Each class gets a stable hue derived from its identity key (same approach as the
on-screen palette). When many classes appear in one print job, hues are nudged
apart so neighbours stay visually distinct while keeping contrast with card text.
"""
from __future__ import annotations

import colorsys
import hashlib

from .class_colour import (
    booking_course_colour_key,
    normalize_class_colour_key,
    unit_component_codes_colour_key,
)
from .models import Booking

# Card text colour in PDF (see timetable_print_pdf).
_PRINT_TEXT_RGB = (0x1A, 0x1A, 0x1A)
_MIN_CONTRAST_RATIO = 3.0
_MIN_HUE_SEP_DEG = 22.0
_MAX_HUE_SEP_DEG = 28.0

HARD_FILL_HEX = "#FFDCDE"
SOFT_FILL_HEX = "#FFF4D6"
_FALLBACK_FILL_HEX = "#E8EBF0"


def print_booking_tint_key(b: Booking, *, by_class: bool) -> str:
    """Stable tint key for print — prefer class identity, never collapse unlike classes."""
    if not by_class:
        code = booking_course_colour_key(b)
        if code:
            return f"course:{code.casefold()}"
        if b.course_id is not None:
            return f"course_id:{b.course_id}"
        return f"booking:{b.id}"

    if b.unit is not None:
        name = (b.unit.name or "").strip()
        if name:
            return normalize_class_colour_key(name)
        codes_key = unit_component_codes_colour_key(b.unit)
        if codes_key:
            return codes_key
    if b.unit_id is not None:
        return f"unit:{b.unit_id}"
    code = booking_course_colour_key(b)
    if code:
        return f"course_fallback:{code.casefold()}"
    return f"booking:{b.id}"


def _hls_to_hex(h: float, l: float, s: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def _srgb_channel(c: int) -> float:
    x = c / 255.0
    return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4


def contrast_ratio_with_print_text(hex_colour: str) -> float:
    """WCAG contrast ratio between a fill and timetable card text."""
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    l_fill = (
        0.2126 * _srgb_channel(r)
        + 0.7152 * _srgb_channel(g)
        + 0.0722 * _srgb_channel(b)
    )
    tr, tg, tb = _PRINT_TEXT_RGB
    l_text = (
        0.2126 * _srgb_channel(tr)
        + 0.7152 * _srgb_channel(tg)
        + 0.0722 * _srgb_channel(tb)
    )
    lighter = max(l_fill, l_text)
    darker = min(l_fill, l_text)
    return (lighter + 0.05) / (darker + 0.05)


def _hash_hue(key: str) -> float:
    """Stable hue on [0, 1) — matches the on-screen class colour scheme."""
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:8]
    return (int(digest, 16) % 360) / 360.0


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b)
    return min(d, 1.0 - d)


def _min_hue_separation(n: int) -> float:
    """Degrees of wheel separation to target for *n* classes in one print job."""
    if n <= 1:
        return 1.0
    ideal_deg = 360.0 / n
    return max(_MIN_HUE_SEP_DEG, min(_MAX_HUE_SEP_DEG, ideal_deg * 0.92)) / 360.0


def _print_hex_from_hue(hue: float) -> str:
    """Pastel fill tuned for small A4 placecards with dark text."""
    for light in (0.82, 0.78, 0.86, 0.80, 0.74):
        for sat in (0.50, 0.45, 0.55, 0.40, 0.48):
            hex_colour = _hls_to_hex(hue, light, sat)
            if contrast_ratio_with_print_text(hex_colour) >= _MIN_CONTRAST_RATIO:
                return hex_colour
    return _FALLBACK_FILL_HEX


def _separated_hue(key: str, assigned_hues: list[float], min_sep: float) -> float:
    """Pick a hue for *key*, nudging away from hues already used in this job."""
    hue = _hash_hue(key)
    if not assigned_hues:
        return hue
    step = max(min_sep, 0.02)
    for _ in range(int(1.0 / step) + 2):
        if all(_hue_distance(hue, other) >= min_sep for other in assigned_hues):
            return hue
        hue = (hue + step) % 1.0
    return hue


def assign_print_colours(keys: set[str]) -> dict[str, str]:
    """Map each tint key to a distinct, readable fill colour.

    Keys are processed in sorted order so the same set always gets the same map.
    Hues start from a per-key hash (global stability) and are nudged apart when
    many classes share one PDF.
    """
    ordered = sorted(k for k in keys if (k or "").strip())
    if not ordered:
        return {}
    min_sep = _min_hue_separation(len(ordered))
    assigned_hues: list[float] = []
    result: dict[str, str] = {}
    for key in ordered:
        hue = _separated_hue(key, assigned_hues, min_sep)
        assigned_hues.append(hue)
        result[key] = _print_hex_from_hue(hue)
    return result


def collect_print_tint_keys(
    bookings: list[Booking],
    *,
    colour_by_class: bool,
) -> set[str]:
    return {print_booking_tint_key(b, by_class=colour_by_class) for b in bookings}


class PrintColourAllocator:
    """Legacy allocator — delegates to :func:`assign_print_colours`."""

    def __init__(self) -> None:
        self._key_to_color: dict[str, str] = {}

    def register_keys(self, keys: set[str]) -> None:
        self._key_to_color.update(assign_print_colours(keys))

    def color_for(self, key: str) -> str:
        if not (key or "").strip():
            key = "?"
        if key not in self._key_to_color:
            self._key_to_color.update(assign_print_colours({key}))
        return self._key_to_color[key]


def build_print_fill_by_booking_id(
    bookings: list[Booking],
    *,
    colour_by_class: bool,
    hard_ids: set[int],
    soft_ids: set[int],
    for_print: bool = False,
    colour_map: dict[str, str] | None = None,
) -> dict[int, str]:
    """One resolved fill per booking before painting."""
    pending: list[tuple[int, str]] = []
    fills: dict[int, str] = {}

    for b in bookings:
        if not for_print and b.id in hard_ids:
            fills[b.id] = HARD_FILL_HEX
            continue
        if not for_print and b.id in soft_ids:
            fills[b.id] = SOFT_FILL_HEX
            continue
        key = print_booking_tint_key(b, by_class=colour_by_class)
        pending.append((b.id, key))

    if colour_map is None:
        colour_map = assign_print_colours({key for _, key in pending})
    for bid, key in pending:
        fills[bid] = colour_map.get(key, _FALLBACK_FILL_HEX)
    return fills


def violation_kind_for_booking(
    booking_id: int,
    *,
    hard_ids: set[int],
    soft_ids: set[int],
) -> str | None:
    if booking_id in hard_ids:
        return "hard"
    if booking_id in soft_ids:
        return "soft"
    return None

"""On-screen booking card colours — more vivid and pairwise distinct within a view.

Print/export can use the same fills via :func:`screen_fill_xlsx` so cards match the UI.
"""
from __future__ import annotations

import colorsys
import hashlib

_CARD_TEXT_RGB = (0x1A, 0x1A, 0x1A)
_MIN_CONTRAST_RATIO = 3.0
_MIN_HUE_SEP_DEG = 24.0
_MAX_HUE_SEP_DEG = 32.0
_FALLBACK_FILL = "#D8DEE8"
_FALLBACK_BORDER = "#5A6470"
_GOLDEN_RATIO = 0.618033988749895

# Saturated qualitative hues (Paul Tol / Tableau); lightened for dark card text.
_VIVID_SOURCE: tuple[str, ...] = (
    "#4477AA",
    "#EE6677",
    "#228833",
    "#CCBB44",
    "#AA3377",
    "#66CCEE",
    "#E15759",
    "#59A14F",
    "#EDC948",
    "#56B4E9",
    "#D55E00",
    "#0072B2",
    "#CC79A7",
    "#009E73",
    "#F0E442",
    "#882255",
    "#332288",
    "#44AA99",
    "#117733",
    "#999933",
    "#661100",
    "#6699CC",
    "#8C564B",
    "#E377C2",
)


def _hls_to_hex(h: float, lightness: float, saturation: float) -> str:
    r, g, b = colorsys.hls_to_rgb(
        h % 1.0,
        max(0.0, min(1.0, lightness)),
        max(0.0, min(1.0, saturation)),
    )
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def _srgb_channel(c: int) -> float:
    x = c / 255.0
    return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4


def _contrast_with_card_text(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    l_fill = (
        0.2126 * _srgb_channel(r)
        + 0.7152 * _srgb_channel(g)
        + 0.0722 * _srgb_channel(b)
    )
    tr, tg, tb = _CARD_TEXT_RGB
    l_text = (
        0.2126 * _srgb_channel(tr)
        + 0.7152 * _srgb_channel(tg)
        + 0.0722 * _srgb_channel(tb)
    )
    lighter = max(l_fill, l_text)
    darker = min(l_fill, l_text)
    return (lighter + 0.05) / (darker + 0.05)


def _light_fill_from_vivid(hex_vivid: str) -> str:
    """Lighten a vivid hex so booking text stays readable."""
    h = hex_vivid.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    hue, _, saturation = colorsys.rgb_to_hls(r, g, b)
    for light in (0.76, 0.72, 0.80, 0.68, 0.74):
        for sat in (min(1.0, saturation * 0.55), 0.62, 0.70, 0.50):
            candidate = _hls_to_hex(hue, light, sat)
            if _contrast_with_card_text(candidate) >= _MIN_CONTRAST_RATIO:
                return candidate
    return _hls_to_hex(hue, 0.74, 0.58)


_SCREEN_FILL_PALETTE: tuple[str, ...] = tuple(
    _light_fill_from_vivid(hex_colour) for hex_colour in _VIVID_SOURCE
)


def _hash_hue(key: str) -> float:
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:8]
    return (int(digest, 16) % 360) / 360.0


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b)
    return min(d, 1.0 - d)


def _min_hue_separation(n: int) -> float:
    if n <= 1:
        return 1.0
    ideal_deg = 360.0 / n
    return max(_MIN_HUE_SEP_DEG, min(_MAX_HUE_SEP_DEG, ideal_deg * 0.92)) / 360.0


def _separated_hue(key: str, assigned_hues: list[float], min_sep: float) -> float:
    hue = _hash_hue(key)
    if not assigned_hues:
        return hue
    step = max(min_sep, 0.02)
    for _ in range(int(1.0 / step) + 2):
        if all(_hue_distance(hue, other) >= min_sep for other in assigned_hues):
            return hue
        hue = (hue + step) % 1.0
    return hue


def _darken_hex(hex_colour: str, *, lightness_scale: float = 0.62) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    return _hls_to_hex(hue, lightness * lightness_scale, min(1.0, saturation * 1.08))


def _best_fill_for_hue(hue: float) -> str:
    # More saturated and slightly less washed-out than the legacy 0.86 / 0.55 pastel.
    for light in (0.74, 0.70, 0.78, 0.66, 0.72):
        for sat in (0.68, 0.62, 0.74, 0.56, 0.70):
            hex_colour = _hls_to_hex(hue, light, sat)
            if _contrast_with_card_text(hex_colour) >= _MIN_CONTRAST_RATIO:
                return hex_colour
    return _FALLBACK_FILL


def _palette_fill_for_index(index: int) -> str:
    return _SCREEN_FILL_PALETTE[index % len(_SCREEN_FILL_PALETTE)]


def _fill_border_from_hue(hue: float, *, palette_index: int | None = None) -> tuple[str, str]:
    if palette_index is not None:
        fill = _palette_fill_for_index(palette_index)
    else:
        fill = _best_fill_for_hue(hue)
    border = _darken_hex(fill)
    if _contrast_with_card_text(fill) < _MIN_CONTRAST_RATIO:
        fill = _FALLBACK_FILL
        border = _FALLBACK_BORDER
    return fill, border


def assign_screen_colours(keys: set[str]) -> dict[str, tuple[str, str]]:
    """Assign distinct (fill, border) hex pairs for all keys in one scope (view or export)."""
    ordered = sorted(k for k in keys if (k or "").strip())
    if not ordered:
        return {}
    result: dict[str, tuple[str, str]] = {}
    for index, key in enumerate(ordered):
        if index < len(_SCREEN_FILL_PALETTE):
            fill = _palette_fill_for_index(index)
        else:
            hue = (index * _GOLDEN_RATIO) % 1.0
            fill = _best_fill_for_hue(hue)
        border = _darken_hex(fill)
        if _contrast_with_card_text(fill) < _MIN_CONTRAST_RATIO:
            fill, border = _FALLBACK_FILL, _FALLBACK_BORDER
        result[key] = (fill, border)
    return result


def screen_colours_for_key(
    key: str,
    colour_map: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """Return ``(#fill, #border)`` for one tint key."""
    if not (key or "").strip():
        key = "?"
    if colour_map and key in colour_map:
        return colour_map[key]
    return _fill_border_from_hue(_hash_hue(key))


def screen_fill_xlsx(key: str, colour_map: dict[str, tuple[str, str]] | None = None) -> str:
    fill, _ = screen_colours_for_key(key, colour_map)
    return f"FF{fill.lstrip('#').upper()}"


def screen_border_xlsx(key: str, colour_map: dict[str, tuple[str, str]] | None = None) -> str:
    _, border = screen_colours_for_key(key, colour_map)
    return f"FF{border.lstrip('#').upper()}"

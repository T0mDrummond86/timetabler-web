"""Stable pastel colours for booking cards (matches desktop ``style.py``)."""
from __future__ import annotations

import colorsys
import hashlib


def _rgb_hex(r: float, g: float, b: float) -> str:
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def class_colours(key: str) -> tuple[str, str]:
    """Return (fill_hex, border_hex) for a class tint key."""
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:6], 16)
    hue = (h % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.86, 0.55)
    fill = _rgb_hex(r, g, b)
    r, g, b = colorsys.hls_to_rgb(hue, 0.55, 0.55)
    border = _rgb_hex(r, g, b)
    return fill, border

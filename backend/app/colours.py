"""Stable booking card colours (matches desktop ``style.py`` / ``screen_colours``)."""
from __future__ import annotations

from timetable.core.screen_colours import assign_screen_colours, screen_colours_for_key

__all__ = ["assign_screen_colours", "class_colours", "screen_colours_for_key"]


def class_colours(
    key: str,
    colour_map: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """Return (fill_hex, border_hex) for a class tint key."""
    return screen_colours_for_key(key, colour_map)

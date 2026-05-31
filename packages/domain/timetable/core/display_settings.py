"""Persisted UI/export preferences (no Qt dependency except QSettings)."""
from __future__ import annotations

COLOUR_BY_CLASS_KEY = "colour_by_class"
_SETTINGS_ORG = "JoondalupTimetable"
_SETTINGS_APP = "App"


def read_colour_by_class(*, default: bool = True) -> bool:
    """Read whether timetables tint by class (True) or course (False)."""
    try:
        from PySide6.QtCore import QSettings

        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        value = settings.value(COLOUR_BY_CLASS_KEY)
    except Exception:
        return default
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes")


def write_colour_by_class(by_class: bool) -> None:
    try:
        from PySide6.QtCore import QSettings

        QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(COLOUR_BY_CLASS_KEY, by_class)
    except Exception:
        pass


def resolve_export_colour_by_class(explicit: bool | None = None) -> bool:
    """Explicit argument wins; otherwise use the saved user preference."""
    if explicit is not None:
        return explicit
    return read_colour_by_class()

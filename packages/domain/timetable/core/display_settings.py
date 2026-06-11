"""Persisted UI/export preferences (no Qt dependency except QSettings)."""
from __future__ import annotations

from ..branding import LEGACY_QSETTINGS_ORG, QSETTINGS_APP, QSETTINGS_ORG

COLOUR_BY_CLASS_KEY = "colour_by_class"


def read_colour_by_class(*, default: bool = True) -> bool:
    """Read whether timetables tint by class (True) or course (False)."""
    try:
        from PySide6.QtCore import QSettings

        settings = QSettings(QSETTINGS_ORG, QSETTINGS_APP)
        if settings.value(COLOUR_BY_CLASS_KEY) is None:
            settings = QSettings(LEGACY_QSETTINGS_ORG, QSETTINGS_APP)
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

        QSettings(QSETTINGS_ORG, QSETTINGS_APP).setValue(COLOUR_BY_CLASS_KEY, by_class)
    except Exception:
        pass


def resolve_export_colour_by_class(explicit: bool | None = None) -> bool:
    """Explicit argument wins; otherwise use the saved user preference."""
    if explicit is not None:
        return explicit
    return read_colour_by_class()

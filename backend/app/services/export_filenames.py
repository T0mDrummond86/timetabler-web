"""Download filenames for session exports."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from timetable.core.tenancy_models import TimetableSession

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_COLLAPSE_WHITESPACE = re.compile(r"\s+")


def timetable_session_name(db: Session, timetable_session_id: int) -> str:
    row = db.get(TimetableSession, timetable_session_id)
    if row is None or not (row.name or "").strip():
        return "session"
    return row.name.strip()


def session_export_filename(session_name: str, ext: str, *, label: str | None = None) -> str:
    """Build a safe attachment filename; optional label distinguishes export types."""
    if not ext.startswith("."):
        ext = f".{ext}"
    stem = _sanitize_stem(session_name)
    if label:
        label = label.strip()
        stem = f"{stem} {label}" if label else stem
    filename = f"{stem}{ext}"
    if len(filename) <= 240:
        return filename
    if label:
        label_part = f" {label}"
        max_name = 240 - len(label_part) - len(ext)
        stem = _sanitize_stem(session_name)[: max(1, max_name)]
        return f"{stem}{label_part}{ext}"
    return f"{stem[: 240 - len(ext)]}{ext}"


def _sanitize_stem(name: str) -> str:
    stem = _INVALID_FILENAME_CHARS.sub("", name.strip())
    stem = _COLLAPSE_WHITESPACE.sub(" ", stem).strip(" .")
    return stem or "session"

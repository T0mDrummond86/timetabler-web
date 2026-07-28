"""Download filenames for session exports."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

from sqlalchemy.orm import Session

from timetable.core.tenancy_models import TimetableSession

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_COLLAPSE_WHITESPACE = re.compile(r"\s+")

# Punctuation that people routinely paste into session names but which has no
# latin-1 equivalent. Mapped to plain ASCII for the fallback filename.
_ASCII_LOOKALIKES = str.maketrans(
    {
        "—": "-",  # em dash
        "–": "-",  # en dash
        "‒": "-",
        "‐": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        " ": " ",
    }
)


def content_disposition(filename: str) -> str:
    """Build an attachment header that survives non-ASCII session names.

    HTTP headers are latin-1 encoded, so a name like "Term 1 — Cyber" would
    raise UnicodeEncodeError on send. Per RFC 6266 we emit an ASCII-safe
    ``filename`` for old clients plus a UTF-8 ``filename*`` that every current
    browser prefers, so the download keeps its real name.
    """
    ascii_name = filename.translate(_ASCII_LOOKALIKES)
    ascii_name = unicodedata.normalize("NFKD", ascii_name)
    ascii_name = ascii_name.encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace('"', "").replace("\\", "")
    ascii_name = _COLLAPSE_WHITESPACE.sub(" ", ascii_name).strip()
    if not ascii_name or ascii_name.startswith("."):
        ascii_name = f"export{ascii_name}" if ascii_name else "export"
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


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

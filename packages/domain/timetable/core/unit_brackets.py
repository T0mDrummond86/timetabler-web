"""Move ``(…)`` unit-code segments from ``Unit.name`` into ``Unit.component_codes``.

Handles:
- ``Title (CODE)`` at end of the name (cut trailing brackets).
- ``Title (CODE) more words`` — code in brackets, descriptive text after (your case).

Skips tiny letter-only chunks like ``(Lab)``. Used after imports and from the Classes tab.

``normalize_component_codes_commas`` keeps the units column comma-separated when the sheet
used spaces, semicolons, or glued codes (e.g. ``VU23220ICTICT443``).
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from .models import Unit

_FULLWIDTH_PAREN_MAP = str.maketrans({
    "\uff08": "(",
    "\uff09": ")",
})


def normalize_class_label_for_parse(raw: str) -> str:
    """Normalise fullwidth parentheses and invisible characters before parsing."""
    s = (raw or "").strip()
    if not s:
        return s
    s = s.translate(_FULLWIDTH_PAREN_MAP)
    for zw in ("\u200b", "\u200c", "\u200d", "\ufeff"):
        s = s.replace(zw, "")
    return s.strip()


def _skip_inner_as_lab_style(inner: str) -> bool:
    """Skip ``(Lab)``, ``(Labs)``, and similar; keep real codes with digits or length ≥ 5."""
    t = inner.strip()
    if not t:
        return True
    if len(t) <= 3 and t.isalpha():
        return True
    if len(t) <= 4 and t.isalpha() and not any(ch.isdigit() for ch in t):
        return True
    return False


def naive_trailing_parenthetical(raw: str) -> tuple[str, str | None]:
    """Last balanced ``( … )`` when the string **ends** with ``)``."""
    s = normalize_class_label_for_parse(raw)
    if not s or s[-1] != ")":
        return s, None
    end = len(s) - 1
    depth = 0
    for i in range(end - 1, -1, -1):
        if s[i] == ")":
            depth += 1
        elif s[i] == "(":
            if depth == 0:
                inner = s[i + 1 : end].strip()
                title = s[:i].strip()
                if not title or not inner:
                    return s, None
                if _skip_inner_as_lab_style(inner):
                    return s, None
                return title, inner
            depth -= 1
    return s, None


def _peel_one_embedded_or_trailing(s: str) -> tuple[str, str | None]:
    """Remove one ``(inner)`` segment: either trailing-only or ``(inner)`` before trailing text."""
    s = normalize_class_label_for_parse(s).strip()
    if not s:
        return s, None

    last_close = s.rfind(")")
    if last_close == -1:
        return s, None

    # Ends with ) → trailing parenthetical only
    if last_close == len(s) - 1:
        return naive_trailing_parenthetical(s)

    after_paren = s[last_close + 1 :].strip()
    if not after_paren:
        return naive_trailing_parenthetical(s)

    depth = 0
    for i in range(last_close, -1, -1):
        if s[i] == ")":
            depth += 1
        elif s[i] == "(":
            depth -= 1
            if depth == 0:
                inner = s[i + 1 : last_close].strip()
                before = s[:i].strip()
                if not inner:
                    return s, None
                if _skip_inner_as_lab_style(inner):
                    return s, None
                new_name = " ".join(x for x in (before, after_paren) if x).strip()
                new_name = re.sub(r"\s+", " ", new_name)
                if not new_name:
                    return s, None
                return new_name, inner
    return s, None


def peel_all_unit_segments_from_name(raw: str) -> tuple[str, list[str]]:
    """Repeatedly peel ``(code)`` segments (trailing or before suffix text)."""
    cur = normalize_class_label_for_parse(raw).strip()
    parts: list[str] = []
    for _ in range(24):
        nxt, seg = _peel_one_embedded_or_trailing(cur)
        if seg is None or nxt == cur:
            break
        parts.append(seg)
        cur = nxt
    return cur, parts


def split_class_title_and_unit_codes(raw: str) -> tuple[str, str | None]:
    """Return ``(name_after_all_peels, comma_joined_codes)`` or ``(raw, None)``."""
    final, parts = peel_all_unit_segments_from_name(raw)
    if not parts:
        return normalize_class_label_for_parse(raw).strip() or raw, None
    return final, ", ".join(parts)


def _merge_units_field(existing: str, piece: str) -> str:
    """Paste into Units: empty → replace; else append if new."""
    e = (existing or "").strip()
    p = (piece or "").strip()
    if not p:
        return (normalize_component_codes_commas(e) or e).strip()
    if not e:
        out = p
    elif p == e or p in e:
        out = e
    elif e in p:
        out = p
    else:
        out = f"{e}, {p}"
    return (normalize_component_codes_commas(out) or out).strip()


# Glued pairs common on timetable strips (no comma / space between codes).
_GLUE_PAIR_RES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(VU\d{4,})(ICT[A-Za-z0-9]{2,})", re.I), r"\1, \2"),
    (re.compile(r"(ICT[A-Za-z0-9]{3,})(VU\d{4,})", re.I), r"\1, \2"),
    (re.compile(r"(\d{4,})([A-Z]{2,}\d[A-Za-z0-9]*)", re.I), r"\1, \2"),
)


def normalize_component_codes_commas(text: str | None) -> str | None:
    """Return ``component_codes`` text with every distinct code separated by ``, ``.

    Handles spaces, semicolons, slashes, and common glued pairs (e.g. ``VU23220ICTICT443``).
    """
    if text is None:
        return None
    s = " ".join(str(text).split())
    if not s:
        return None
    s = s.replace(";", ",").replace("/", ",").replace("|", ",")
    for _ in range(24):
        t = re.sub(r"([0-9A-Za-z._-])\s+([0-9A-Za-z])", r"\1, \2", s)
        if t == s:
            break
        s = t
    for _ in range(12):
        prev = s
        for pat, repl in _GLUE_PAIR_RES:
            s = pat.sub(repl, s)
        if s == prev:
            break
    s = re.sub(r",\s*,+", ", ", s).strip().strip(",")
    bits = [b.strip() for b in s.split(",") if b.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for b in bits:
        k = b.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(b)
    joined = ", ".join(out)
    return joined if joined else None


def apply_unit_bracket_fields_from_names(session: Session) -> int:
    """Move bracketed code segment(s) from each ``Unit.name`` into ``component_codes``."""
    touched = 0
    for u in list(session.query(Unit).order_by(Unit.id)):
        raw = (u.name or "").strip()
        if not raw:
            continue
        final_title, segments = peel_all_unit_segments_from_name(raw)
        if not segments:
            continue
        other = (
            session.query(Unit)
            .filter(Unit.name == final_title, Unit.id != u.id)
            .first()
        )
        row_changed = False
        prev_codes = (u.component_codes or "").strip()
        merged = prev_codes
        for seg in segments:
            merged = _merge_units_field(merged, seg).strip()
        if other is None:
            if u.name != final_title:
                u.name = final_title
                row_changed = True
            if merged != prev_codes:
                u.component_codes = merged or None
                row_changed = True
        else:
            if merged != prev_codes:
                u.component_codes = merged or None
                row_changed = True
        if row_changed:
            touched += 1
    for u in list(session.query(Unit).order_by(Unit.id)):
        if not u.component_codes:
            continue
        nn = normalize_component_codes_commas(u.component_codes)
        cur = (u.component_codes or "").strip()
        if nn is not None and nn != cur:
            u.component_codes = nn
            touched += 1
    if touched:
        session.flush()
    return touched

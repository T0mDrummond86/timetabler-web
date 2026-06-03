"""Build timetabling-only change-log rows for the UI and for Excel export."""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .booking_snapshots import timetabling_changelog_rows
from .changelog import TIMETABLING_LOG_ACTIONS, resolve_session_booking_net_maps
from .models import ChangeLogEntry


@dataclass(frozen=True)
class ChangeLogDisplayRow:
    when: str
    action: str
    row: dict[str, str]
    booking_id: int
    entry_id: int | None
    note: str


def is_timetabling_change_log_entry(entry: ChangeLogEntry) -> bool:
    if entry.action not in TIMETABLING_LOG_ACTIONS or not entry.details:
        return False
    try:
        payload = json.loads(entry.details)
    except Exception:
        return False
    return isinstance(payload, dict) and isinstance(payload.get("bookings"), dict)


def payload_booking_maps(payload: dict) -> tuple[dict[int, dict | None], dict[int, dict | None]]:
    before: dict[int, dict | None] = {}
    after: dict[int, dict | None] = {}
    bookings = payload.get("bookings")
    if not isinstance(bookings, dict):
        return before, after
    for bid_str, snap in bookings.items():
        try:
            bid = int(bid_str)
        except ValueError:
            continue
        if isinstance(snap, dict):
            before[bid] = snap.get("before")
            after[bid] = snap.get("after")
    return before, after


def _payload_notes(payload: dict) -> dict[int, str]:
    notes = payload.get("notes")
    if not isinstance(notes, dict):
        return {}
    out: dict[int, str] = {}
    for bid_str, txt in notes.items():
        try:
            bid = int(bid_str)
        except ValueError:
            continue
        t = str(txt or "").strip()
        if t:
            out[bid] = t
    return out


def _session_entries_query(session: Session, timetable_session_id: int):
    return (
        session.query(ChangeLogEntry)
        .filter(ChangeLogEntry.timetable_session_id == timetable_session_id)
        .order_by(ChangeLogEntry.id)
    )


def gather_timetabling_change_log_display_rows(
    session: Session,
    *,
    timetable_session_id: int,
    resolved: bool,
) -> list[ChangeLogDisplayRow]:
    if resolved:
        before_map, after_map = resolve_session_booking_net_maps(
            session, timetable_session_id=timetable_session_id
        )
        rows = timetabling_changelog_rows(session, before_map, after_map)
        bids = sorted(set(before_map) | set(after_map))
        latest_entry_for_bid: dict[int, int] = {}
        latest_note_for_bid: dict[int, str] = {}
        entries = _session_entries_query(session, timetable_session_id).order_by(
            ChangeLogEntry.id.desc()
        ).all()
        for e in entries:
            if not is_timetabling_change_log_entry(e):
                continue
            try:
                payload = json.loads(e.details or "")
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            b_before, b_after = payload_booking_maps(payload)
            for bid in set(b_before) | set(b_after):
                if bid not in latest_entry_for_bid:
                    latest_entry_for_bid[bid] = e.id
            notes = _payload_notes(payload)
            for bid in notes:
                if bid not in latest_note_for_bid:
                    latest_note_for_bid[bid] = notes[bid]
        out: list[ChangeLogDisplayRow] = []
        for i, row in enumerate(rows):
            bid = bids[i] if i < len(bids) else -1
            out.append(
                ChangeLogDisplayRow(
                    when="",
                    action="net",
                    row=row,
                    booking_id=bid,
                    entry_id=latest_entry_for_bid.get(bid),
                    note=latest_note_for_bid.get(bid, ""),
                )
            )
        return out

    out: list[ChangeLogDisplayRow] = []
    entries = (
        _session_entries_query(session, timetable_session_id)
        .order_by(ChangeLogEntry.id.desc())
        .all()
    )
    for e in entries:
        if not is_timetabling_change_log_entry(e):
            continue
        try:
            payload = json.loads(e.details or "")
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        before, after = payload_booking_maps(payload)
        if not before and not after:
            continue
        notes = _payload_notes(payload)
        ts = e.ts.strftime("%Y-%m-%d %H:%M:%S") if e.ts else ""
        rows = timetabling_changelog_rows(session, before, after)
        bids = sorted(set(before) | set(after))
        for i, row in enumerate(rows):
            bid = bids[i] if i < len(bids) else -1
            out.append(
                ChangeLogDisplayRow(
                    when=ts,
                    action=e.action,
                    row=row,
                    booking_id=bid,
                    entry_id=e.id,
                    note=notes.get(bid, ""),
                )
            )
    return out


def set_change_log_note(
    session: Session,
    *,
    timetable_session_id: int,
    entry_id: int,
    booking_id: int,
    note: str,
) -> None:
    """Persist note text inside ChangeLogEntry.details['notes'][booking_id]."""
    entry = session.get(ChangeLogEntry, entry_id)
    if entry is None or entry.timetable_session_id != timetable_session_id:
        return
    try:
        payload = json.loads(entry.details or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    notes = payload.get("notes")
    if not isinstance(notes, dict):
        notes = {}
    key = str(booking_id)
    text = note.strip()
    if text:
        notes[key] = text
    else:
        notes.pop(key, None)
    if notes:
        payload["notes"] = notes
    else:
        payload.pop("notes", None)
    entry.details = json.dumps(payload) if payload else None


CHANGE_LOG_EXPORT_HEADERS = [
    "ID",
    "group",
    "class",
    "lecturer change",
    "time change",
    "day change",
    "room change",
    "delete",
    "When",
    "Action",
]

"""Build timetabling-only change-log rows for the UI and for Excel export."""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .booking_snapshots import timetabling_changelog_rows
from .changelog import TIMETABLING_LOG_ACTIONS, resolve_session_booking_net_maps
from .models import Booking, ChangeLogEntry


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


# Hand-written records for changes actioned outside this session's tracking
# (e.g. on a previous version of the file). They carry a display row rather
# than before/after snapshots, and always surface on the resolved view.
MANUAL_LOG_ACTION = "manual"


def is_manual_change_log_entry(entry: ChangeLogEntry) -> bool:
    if entry.action != MANUAL_LOG_ACTION or not entry.details:
        return False
    try:
        payload = json.loads(entry.details)
    except Exception:
        return False
    return isinstance(payload, dict) and isinstance(payload.get("row"), dict)


def _manual_display_row(entry: ChangeLogEntry) -> ChangeLogDisplayRow | None:
    if not is_manual_change_log_entry(entry):
        return None
    payload = json.loads(entry.details or "{}")
    from .booking_snapshots import TIMETABLING_TABLE_KEYS

    stored = payload.get("row") or {}
    row = {key: str(stored.get(key, "") or "") for key in TIMETABLING_TABLE_KEYS}
    booking_id = payload.get("booking_id")
    bid = int(booking_id) if isinstance(booking_id, int) else -1
    notes = _payload_notes(payload)
    return ChangeLogDisplayRow(
        when=entry.ts.strftime("%Y-%m-%d %H:%M:%S") if entry.ts else "",
        action=MANUAL_LOG_ACTION,
        row=row,
        booking_id=bid,
        entry_id=entry.id,
        note=notes.get(bid, ""),
    )


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


def _course_ids_from_booking_states(*states: dict | None) -> set[int]:
    ids: set[int] = set()
    for state in states:
        if not state:
            continue
        cid = state.get("course_id")
        if cid is not None:
            ids.add(int(cid))
    return ids


def _manual_entry_bookings(
    session: Session, timetable_session_id: int
) -> list[tuple[dict, Booking]]:
    """(payload, live booking) pairs for manual records whose booking still exists."""
    out: list[tuple[dict, Booking]] = []
    for entry in _session_entries_query(session, timetable_session_id).all():
        if not is_manual_change_log_entry(entry):
            continue
        payload = json.loads(entry.details or "{}")
        booking_id = payload.get("booking_id")
        if not isinstance(booking_id, int):
            continue
        booking = session.get(Booking, booking_id)
        if booking is None:
            continue
        out.append((payload, booking))
    return out


def affected_course_ids_from_resolved_changelog(
    session: Session,
    *,
    timetable_session_id: int,
) -> set[int]:
    """Course ids with net booking changes in the session change log (resolved view)."""
    before_map, after_map = resolve_session_booking_net_maps(
        session, timetable_session_id=timetable_session_id
    )
    course_ids: set[int] = set()
    for bid in set(before_map) | set(after_map):
        course_ids |= _course_ids_from_booking_states(before_map.get(bid), after_map.get(bid))
    # Manual records mark their course as changed too (changes-only exports).
    for _payload, booking in _manual_entry_bookings(session, timetable_session_id):
        if booking.course_id is not None:
            course_ids.add(int(booking.course_id))
    return course_ids


@dataclass(frozen=True)
class AdminExportChangeHighlight:
    """Which admin-export label cells to tint red for a class-card event id."""

    time: bool = False
    lecturer: bool = False
    room: bool = False
    day_header_days: frozenset[int] = frozenset()


def _card_id_from_state(state: dict | None) -> str:
    if not state:
        return ""
    raw = state.get("external_id")
    if raw is None:
        return ""
    return str(raw).strip()


def _highlight_from_net_states(
    b_state: dict | None, a_state: dict
) -> AdminExportChangeHighlight:
    """Derive highlight flags from resolved before/after booking snapshots."""
    if b_state is None:
        return AdminExportChangeHighlight(
            time=True,
            lecturer=bool(a_state.get("staff_id") or a_state.get("sfs_co_teacher_staff_id")),
            room=bool(a_state.get("room_id")),
            day_header_days=frozenset({int(a_state["day"])}),
        )
    days: set[int] = set()
    if int(b_state["day"]) != int(a_state["day"]):
        days.add(int(b_state["day"]))
        days.add(int(a_state["day"]))
    return AdminExportChangeHighlight(
        time=(int(b_state["start_slot"]), int(b_state["end_slot"]))
        != (int(a_state["start_slot"]), int(a_state["end_slot"])),
        lecturer=int(b_state.get("staff_id") or 0) != int(a_state.get("staff_id") or 0)
        or int(b_state.get("sfs_co_teacher_staff_id") or 0)
        != int(a_state.get("sfs_co_teacher_staff_id") or 0),
        room=int(b_state.get("room_id") or 0) != int(a_state.get("room_id") or 0),
        day_header_days=frozenset(days),
    )


def admin_export_highlights_by_external_id(
    session: Session,
    *,
    timetable_session_id: int,
) -> dict[str, AdminExportChangeHighlight]:
    """Resolved net timetabling changes keyed by class-card id (``Booking.external_id``).

    Entries without an event id are omitted. Deleted classes are omitted (not on export).
    """
    before_map, after_map = resolve_session_booking_net_maps(
        session, timetable_session_id=timetable_session_id
    )
    out: dict[str, AdminExportChangeHighlight] = {}
    for bid in set(before_map) | set(after_map):
        b_state = before_map.get(bid)
        a_state = after_map.get(bid)
        if a_state is None:
            continue
        eid = _card_id_from_state(a_state) or _card_id_from_state(b_state)
        if not eid:
            continue
        flags = _highlight_from_net_states(b_state, a_state)
        if flags.time or flags.lecturer or flags.room or flags.day_header_days:
            out[eid] = flags

    # Manual records highlight exactly the fields chosen when they were logged
    # (day → the booking's current day header). Legacy records without a
    # fields list flag the whole card.
    for payload, booking in _manual_entry_bookings(session, timetable_session_id):
        eid = (booking.external_id or "").strip()
        if not eid:
            continue
        chosen = payload.get("fields")
        if isinstance(chosen, list):
            time_c = "time" in chosen
            lecturer = "lecturer" in chosen
            room = "room" in chosen
            day = "day" in chosen
        else:
            time_c = lecturer = room = True
            day = False
        flags = AdminExportChangeHighlight(
            time=time_c,
            lecturer=lecturer,
            room=room,
            day_header_days=frozenset({int(booking.day)}) if day else frozenset(),
        )
        existing = out.get(eid)
        if existing is not None:
            flags = AdminExportChangeHighlight(
                time=existing.time or flags.time,
                lecturer=existing.lecturer or flags.lecturer,
                room=existing.room or flags.room,
                day_header_days=existing.day_header_days | flags.day_header_days,
            )
        out[eid] = flags
    return out


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
        # Manual records always surface on the resolved view, even when the
        # booking's tracked state shows no net change (oldest first).
        for e in reversed(entries):
            manual = _manual_display_row(e)
            if manual is not None:
                out.append(manual)
        return out

    out: list[ChangeLogDisplayRow] = []
    entries = (
        _session_entries_query(session, timetable_session_id)
        .order_by(ChangeLogEntry.id.desc())
        .all()
    )
    for e in entries:
        manual = _manual_display_row(e)
        if manual is not None:
            out.append(manual)
            continue
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

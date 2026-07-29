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
    # True when this change has been removed from the admin-export markup. It
    # still appears in the log (shown with a "removed" status) but no longer
    # contributes a highlight.
    removed: bool = False
    # Every lecturer this change touches — the staff (and co-teacher) on the
    # booking before and after. Populated even when the change itself wasn't a
    # lecturer swap, so a room or time move still names who has to be told.
    lecturers: tuple[str, ...] = ()
    # The booking as it now stands: lecturer/time/day/room keys, always filled.
    # ``row`` only carries the fields that changed, so this is what a
    # notification needs — the full class detail, not just the delta.
    current: dict[str, str] | None = None


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
        removed=payload.get("manual_removed") is True,
    )


def _staff_ids_from_states(*states: dict | None) -> set[int]:
    """Staff and co-teacher ids referenced by any of the given booking states."""
    out: set[int] = set()
    for state in states:
        if not state:
            continue
        for key in ("staff_id", "sfs_co_teacher_staff_id"):
            try:
                sid = int(state.get(key) or 0)
            except (TypeError, ValueError):
                continue
            if sid:
                out.add(sid)
    return out


def _booking_staff_ids(session: Session, booking_ids: set[int]) -> dict[int, set[int]]:
    """Current staff/co-teacher ids per booking — used for manual records, which
    store a display row rather than before/after snapshots."""
    out: dict[int, set[int]] = {}
    real = [b for b in booking_ids if b and b > 0]
    if not real:
        return out
    for b in session.query(Booking).filter(Booking.id.in_(real)).all():
        out[b.id] = _staff_ids_from_states(
            {
                "staff_id": b.staff_id,
                "sfs_co_teacher_staff_id": getattr(b, "sfs_co_teacher_staff_id", None),
            }
        )
    return out


CURRENT_KEYS = ("lecturer", "time", "day", "room")


def _current_from_states(
    session: Session, states: list[dict | None]
) -> list[dict[str, str]]:
    """Render each booking's standing lecturer/time/day/room, resolving names in
    one query. A deleted booking falls back to its last known state."""
    from ..constants import DAYS
    from .booking_snapshots import _name_lookup, _slot_to_str
    from .models import Room, Staff

    staff_ids: set[int | None] = set()
    room_ids: set[int | None] = set()
    for state in states:
        if state:
            staff_ids.add(state.get("staff_id"))
            room_ids.add(state.get("room_id"))
    staff = _name_lookup(session, Staff, staff_ids)
    rooms = _name_lookup(session, Room, room_ids)

    out: list[dict[str, str]] = []
    for state in states:
        if not state:
            out.append({key: "" for key in CURRENT_KEYS})
            continue
        try:
            day = DAYS[int(state.get("day", -1))]
        except (IndexError, TypeError, ValueError):
            day = ""
        try:
            time = (
                f"{_slot_to_str(int(state['start_slot']))}"
                f"–{_slot_to_str(int(state['end_slot']))}"
            )
        except (KeyError, TypeError, ValueError):
            time = ""
        lecturer = staff.get(state.get("staff_id"), "")
        room = rooms.get(state.get("room_id"), "")
        out.append(
            {
                "lecturer": "" if lecturer in ("—", "?") else lecturer,
                "time": time,
                "day": day,
                "room": "" if room in ("—", "?") else room,
            }
        )
    return out


def _booking_states(session: Session, booking_ids: set[int]) -> dict[int, dict]:
    """Live state for bookings that still exist — used for manual records, which
    store a display row rather than before/after snapshots."""
    out: dict[int, dict] = {}
    real = [b for b in booking_ids if b and b > 0]
    if not real:
        return out
    for b in session.query(Booking).filter(Booking.id.in_(real)).all():
        out[b.id] = {
            "staff_id": b.staff_id,
            "room_id": b.room_id,
            "day": b.day,
            "start_slot": b.start_slot,
            "end_slot": b.end_slot,
        }
    return out


def _with_lecturer_names(
    session: Session,
    rows: list[ChangeLogDisplayRow],
    staff_id_sets: list[set[int]],
    current_states: list[dict | None],
) -> list[ChangeLogDisplayRow]:
    """Resolve the collected staff ids to names in one query and attach them,
    along with each booking's standing lecturer/time/day/room."""
    from dataclasses import replace

    from .booking_snapshots import _name_lookup
    from .models import Staff

    all_ids: set[int | None] = set()
    for ids in staff_id_sets:
        all_ids |= set(ids)
    names = _name_lookup(session, Staff, all_ids)
    currents = _current_from_states(session, current_states)
    out: list[ChangeLogDisplayRow] = []
    for row, ids, current in zip(rows, staff_id_sets, currents):
        labels = sorted(
            {
                name
                for sid in ids
                if (name := names.get(sid)) and name not in ("—", "?")
            }
        )
        out.append(replace(row, lecturers=tuple(labels), current=current))
    return out


def _latest_entry_for_bookings(
    session: Session, timetable_session_id: int
) -> dict[int, int]:
    """Booking id -> id of the most recent entry that changed it."""
    out: dict[int, int] = {}
    entries = (
        session.query(ChangeLogEntry)
        .filter(ChangeLogEntry.timetable_session_id == timetable_session_id)
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
        for bid in set(before) | set(after):
            # Newest first, so the first sighting is the latest change.
            out.setdefault(bid, e.id)
    return out


def _removed_net_pins(session: Session, timetable_session_id: int) -> dict[int, int]:
    """Booking id -> the change its removal was applied to.

    A removal is recorded on the entry that was the booking's latest change at
    the time, under ``details['removed_net']``. Pinning it to that entry is
    what makes removal apply to *one* change rather than to the booking
    forever: once the class is changed again, a newer entry becomes its latest,
    the pin no longer matches, and the new change is logged and marked up
    normally. Removing that one too is a separate, deliberate act.
    """
    out: dict[int, int] = {}
    for entry in _session_entries_query(session, timetable_session_id):
        try:
            payload = json.loads(entry.details or "{}")
        except Exception:
            continue
        removed = payload.get("removed_net") if isinstance(payload, dict) else None
        if not isinstance(removed, dict):
            continue
        for key, val in removed.items():
            if not val:
                continue
            try:
                bid = int(key)
            except (TypeError, ValueError):
                continue
            # Later removals win if a booking was removed more than once.
            if entry.id is not None and entry.id > out.get(bid, -1):
                out[bid] = entry.id
    return out


def _removed_booking_ids_for_latest(
    session: Session,
    timetable_session_id: int,
    latest_entry_for_bid: dict[int, int],
) -> set[int]:
    """Bookings whose *current* net change is the one that was removed."""
    pins = _removed_net_pins(session, timetable_session_id)
    return {
        bid
        for bid, pinned in pins.items()
        if latest_entry_for_bid.get(bid) == pinned
    }


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
    removed_net = _removed_booking_ids_for_latest(
        session,
        timetable_session_id,
        _latest_entry_for_bookings(session, timetable_session_id),
    )
    course_ids: set[int] = set()
    for bid in set(before_map) | set(after_map):
        if bid in removed_net:
            continue
        course_ids |= _course_ids_from_booking_states(before_map.get(bid), after_map.get(bid))
    # Manual records mark their course as changed too (changes-only exports),
    # unless they've been removed from the markup.
    for payload, booking in _manual_entry_bookings(session, timetable_session_id):
        if payload.get("manual_removed") is True:
            continue
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
    removed_net = _removed_booking_ids_for_latest(
        session,
        timetable_session_id,
        _latest_entry_for_bookings(session, timetable_session_id),
    )
    out: dict[str, AdminExportChangeHighlight] = {}
    for bid in set(before_map) | set(after_map):
        if bid in removed_net:
            continue  # removed from the markup, but still shown in the log
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
    # (day → the booking's current day header). Records without a stored
    # selection (made before the field picker existed) highlight nothing —
    # remove and re-log them to choose fields.
    for payload, booking in _manual_entry_bookings(session, timetable_session_id):
        if payload.get("manual_removed") is True:
            continue  # removed from the markup, but still shown in the log
        eid = (booking.external_id or "").strip()
        if not eid:
            continue
        chosen = payload.get("fields")
        if not isinstance(chosen, list):
            continue
        time_c = "time" in chosen
        lecturer = "lecturer" in chosen
        room = "room" in chosen
        day = "day" in chosen
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
        # Newest first, so the first entry seen for a booking is its latest change.
        entries = (
            session.query(ChangeLogEntry)
            .filter(ChangeLogEntry.timetable_session_id == timetable_session_id)
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
            b_before, b_after = payload_booking_maps(payload)
            for bid in set(b_before) | set(b_after):
                if bid not in latest_entry_for_bid:
                    latest_entry_for_bid[bid] = e.id
            notes = _payload_notes(payload)
            for bid in notes:
                if bid not in latest_note_for_bid:
                    latest_note_for_bid[bid] = notes[bid]
        removed_net = _removed_booking_ids_for_latest(
            session, timetable_session_id, latest_entry_for_bid
        )
        out: list[ChangeLogDisplayRow] = []
        staff_ids: list[set[int]] = []
        current_states: list[dict | None] = []
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
                    removed=bid in removed_net,
                )
            )
            staff_ids.append(_staff_ids_from_states(before_map.get(bid), after_map.get(bid)))
            # "After" is where the booking now stands; a deleted one falls back
            # to its last known state.
            current_states.append(after_map.get(bid) or before_map.get(bid))
        # Manual records always surface on the resolved view, even when the
        # booking's tracked state shows no net change.
        manual_rows = [r for r in (_manual_display_row(e) for e in entries) if r is not None]
        manual_bids = {r.booking_id for r in manual_rows}
        manual_staff = _booking_staff_ids(session, manual_bids)
        manual_states = _booking_states(session, manual_bids)
        for manual in manual_rows:
            out.append(manual)
            staff_ids.append(manual_staff.get(manual.booking_id, set()))
            current_states.append(manual_states.get(manual.booking_id))
        out = _with_lecturer_names(session, out, staff_ids, current_states)
        # Order the whole resolved view newest-first. Each resolution is keyed by
        # the most recent change that produced it: net rows use the latest change
        # touching that booking; manual rows use their own entry.
        out.sort(key=lambda r: r.entry_id if r.entry_id is not None else -1, reverse=True)
        return out

    out: list[ChangeLogDisplayRow] = []
    staff_ids: list[set[int]] = []
    current_states: list[dict | None] = []
    manual_pending: list[int] = []
    entries = (
        session.query(ChangeLogEntry)
        .filter(ChangeLogEntry.timetable_session_id == timetable_session_id)
        .order_by(ChangeLogEntry.id.desc())
        .all()
    )
    for e in entries:
        manual = _manual_display_row(e)
        if manual is not None:
            out.append(manual)
            # Resolved from the live booking once every entry has been walked.
            manual_pending.append(len(staff_ids))
            staff_ids.append(set())
            current_states.append(None)
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
            staff_ids.append(_staff_ids_from_states(before.get(bid), after.get(bid)))
            current_states.append(after.get(bid) or before.get(bid))
    manual_bids = {out[i].booking_id for i in manual_pending}
    manual_staff = _booking_staff_ids(session, manual_bids)
    manual_states = _booking_states(session, manual_bids)
    for i in manual_pending:
        staff_ids[i] = manual_staff.get(out[i].booking_id, set())
        current_states[i] = manual_states.get(out[i].booking_id)
    return _with_lecturer_names(session, out, staff_ids, current_states)


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

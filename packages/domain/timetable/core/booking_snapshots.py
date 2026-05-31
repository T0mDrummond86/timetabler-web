"""Booking/course snapshot capture, restore, and human-readable diffs."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from ..constants import DAYS, NUM_SLOTS, slot_to_time
from .models import Booking, Course, Room, Staff, Unit

BOOKING_SNAPSHOT_FIELDS = (
    "week_id",
    "course_id",
    "unit_id",
    "staff_id",
    "room_id",
    "day",
    "start_slot",
    "end_slot",
    "notes",
    "in_term_1",
    "in_term_2",
    "online_student_count",
    "external_id",
    "lock_time",
    "lock_staff",
    "session_part",
    "sfs_co_teacher_staff_id",
    "sfs_co_teacher_in_term_1",
    "sfs_co_teacher_in_term_2",
    "session_weeks",
    "block_week_index",
)
COURSE_SNAPSHOT_FIELDS = (
    "code",
    "name",
    "timetable_locked",
    "qualification_id",
    "sidebar_order",
    "block_week_count",
    "block_start_semester_week",
    "is_block_cohort",
)

TIMETABLING_TABLE_KEYS = (
    "id",
    "group",
    "class",
    "lecturer_change",
    "time_change",
    "day_change",
    "room_change",
    "delete",
)


def snapshot_bookings(
    session: Session, booking_ids: Iterable[int]
) -> dict[int, dict | None]:
    """Capture the current state of each booking; None if it does not exist."""
    out: dict[int, dict | None] = {}
    for bid in booking_ids:
        b = session.get(Booking, bid)
        if b is None:
            out[bid] = None
        else:
            out[bid] = {f: getattr(b, f) for f in BOOKING_SNAPSHOT_FIELDS}
    return out


def snapshot_courses(
    session: Session, course_ids: Iterable[int]
) -> dict[int, dict | None]:
    out: dict[int, dict | None] = {}
    for cid in course_ids:
        c = session.get(Course, cid)
        out[cid] = None if c is None else {f: getattr(c, f) for f in COURSE_SNAPSHOT_FIELDS}
    return out


def apply_booking_snapshots(
    session: Session, target: dict[int, dict | None]
) -> None:
    """Restore booking rows from snapshot dicts (None = delete)."""
    for bid, state in target.items():
        existing = session.get(Booking, bid)
        if state is None:
            if existing is not None:
                session.delete(existing)
        elif existing is None:
            session.add(Booking(id=bid, **state))
        else:
            for key, value in state.items():
                setattr(existing, key, value)
    session.commit()


def apply_course_snapshots(
    session: Session,
    target: dict[int, dict | None],
    *,
    adding: bool,
) -> None:
    """Two-phase course restore: first creates/updates, then deletes."""
    for cid, state in target.items():
        existing = session.get(Course, cid)
        if adding:
            if state is not None:
                if existing is None:
                    session.add(Course(id=cid, **state))
                else:
                    for key, value in state.items():
                        setattr(existing, key, value)
        elif state is None and existing is not None:
            session.delete(existing)
    session.commit()


def _slot_to_str(slot: int) -> str:
    if slot >= NUM_SLOTS:
        return "22:00"
    return slot_to_time(slot).strftime("%H:%M")


def _name_lookup(session: Session, model, ids: set[int | None]) -> dict[int | None, str]:
    out: dict[int | None, str] = {None: "—"}
    real = [i for i in ids if i is not None]
    if not real:
        return out
    rows = session.query(model).filter(model.id.in_(real)).all()
    for row in rows:
        if model is Staff:
            out[row.id] = row.name
        else:
            out[row.id] = getattr(row, "code", None) or getattr(row, "name", "?")
    for i in real:
        out.setdefault(i, "?")
    return out


def _card_id_str(state: dict | None) -> str:
    if not state:
        return ""
    raw = state.get("external_id")
    if raw is None:
        return ""
    return str(raw).strip()


def summarise_booking_change(
    before: dict[int, dict | None],
    after: dict[int, dict | None],
    diff_lines: list[str],
) -> str:
    """Short tag describing the dominant change kind (for change-log titles)."""
    n_added = sum(
        1 for bid, state in after.items() if state is not None and before.get(bid) is None
    )
    n_deleted = sum(
        1 for bid, state in before.items() if state is not None and after.get(bid) is None
    )
    if n_added and not n_deleted:
        return f"added {n_added}"
    if n_deleted and not n_added:
        return f"deleted {n_deleted}"
    if n_added and n_deleted:
        return f"+{n_added} / -{n_deleted}"
    kinds: list[str] = []
    for bid in set(before) & set(after):
        b_state = before.get(bid)
        a_state = after.get(bid)
        if not (b_state and a_state):
            continue
        if b_state["staff_id"] != a_state["staff_id"]:
            kinds.append("lecturer")
        if b_state["room_id"] != a_state["room_id"]:
            kinds.append("room")
        if b_state["day"] != a_state["day"]:
            kinds.append("day")
        if (b_state["start_slot"], b_state["end_slot"]) != (
            a_state["start_slot"],
            a_state["end_slot"],
        ):
            kinds.append("time")
        if b_state["course_id"] != a_state["course_id"]:
            kinds.append("course")
        if b_state["unit_id"] != a_state["unit_id"]:
            kinds.append("unit")
        if b_state.get("notes") != a_state.get("notes"):
            kinds.append("note")
    if not kinds:
        return ""
    seen: set[str] = set()
    ordered: list[str] = []
    for kind in kinds:
        if kind not in seen:
            seen.add(kind)
            ordered.append(kind)
    return ", ".join(ordered)


def describe_booking_changes(
    session: Session,
    before: dict[int, dict | None],
    after: dict[int, dict | None],
) -> list[str]:
    """Human-readable per-booking diff lines."""
    lines: list[str] = []
    course_ids: set[int | None] = set()
    unit_ids: set[int | None] = set()
    staff_ids: set[int | None] = set()
    room_ids: set[int | None] = set()
    for state in (*before.values(), *after.values()):
        if not state:
            continue
        course_ids.add(state.get("course_id"))
        unit_ids.add(state.get("unit_id"))
        staff_ids.add(state.get("staff_id"))
        room_ids.add(state.get("room_id"))
    courses = _name_lookup(session, Course, course_ids)
    units = _name_lookup(session, Unit, unit_ids)
    staff = _name_lookup(session, Staff, staff_ids)
    rooms = _name_lookup(session, Room, room_ids)

    def label(state: dict | None) -> str:
        if not state:
            return "—"
        return courses.get(state.get("course_id"), "?")

    for bid in sorted(set(before) | set(after)):
        b_state = before.get(bid)
        a_state = after.get(bid)
        if b_state is None and a_state is not None:
            parts = [
                f"Added booking #{bid}",
                f"course={courses.get(a_state.get('course_id'), '?')}",
                f"unit={units.get(a_state.get('unit_id'), '—')}",
                f"lecturer={staff.get(a_state.get('staff_id'), '—')}",
                f"room={rooms.get(a_state.get('room_id'), '—')}",
                f"day={DAYS[a_state['day']]}",
                f"time={_slot_to_str(a_state['start_slot'])}–{_slot_to_str(a_state['end_slot'])}",
            ]
            lines.append(" · ".join(parts))
            continue
        if b_state is not None and a_state is None:
            lines.append(
                f"Deleted booking #{bid} · course={label(b_state)} · "
                f"day={DAYS[b_state['day']]} "
                f"{_slot_to_str(b_state['start_slot'])}–{_slot_to_str(b_state['end_slot'])}"
            )
            continue
        if b_state == a_state:
            continue
        diff_parts: list[str] = []
        if b_state["course_id"] != a_state["course_id"]:
            diff_parts.append(
                f"Course: {courses.get(b_state['course_id'], '?')} → "
                f"{courses.get(a_state['course_id'], '?')}"
            )
        if b_state["unit_id"] != a_state["unit_id"]:
            diff_parts.append(
                f"Unit: {units.get(b_state['unit_id'], '—')} → "
                f"{units.get(a_state['unit_id'], '—')}"
            )
        if b_state["staff_id"] != a_state["staff_id"]:
            diff_parts.append(
                f"Lecturer: {staff.get(b_state['staff_id'], '—')} → "
                f"{staff.get(a_state['staff_id'], '—')}"
            )
        if b_state["room_id"] != a_state["room_id"]:
            diff_parts.append(
                f"Room: {rooms.get(b_state['room_id'], '—')} → "
                f"{rooms.get(a_state['room_id'], '—')}"
            )
        if b_state["day"] != a_state["day"]:
            diff_parts.append(f"Day: {DAYS[b_state['day']]} → {DAYS[a_state['day']]}")
        if (b_state["start_slot"], b_state["end_slot"]) != (
            a_state["start_slot"],
            a_state["end_slot"],
        ):
            diff_parts.append(
                f"Time: {_slot_to_str(b_state['start_slot'])}–{_slot_to_str(b_state['end_slot'])}"
                f" → {_slot_to_str(a_state['start_slot'])}–{_slot_to_str(a_state['end_slot'])}"
            )
        if b_state.get("notes") != a_state.get("notes"):
            diff_parts.append("Note edited")
        if diff_parts:
            lines.append(f"#{bid} ({label(a_state)}): " + "; ".join(diff_parts))
    return lines


def timetabling_changelog_rows(
    session: Session,
    before: dict[int, dict | None],
    after: dict[int, dict | None],
) -> list[dict[str, str]]:
    """Spreadsheet-style rows for timetabling change logs."""
    rows_out: list[dict[str, str]] = []
    course_ids: set[int | None] = set()
    unit_ids: set[int | None] = set()
    staff_ids: set[int | None] = set()
    room_ids: set[int | None] = set()
    for state in (*before.values(), *after.values()):
        if not state:
            continue
        course_ids.add(state.get("course_id"))
        unit_ids.add(state.get("unit_id"))
        staff_ids.add(state.get("staff_id"))
        room_ids.add(state.get("room_id"))
    courses = _name_lookup(session, Course, course_ids)
    units = _name_lookup(session, Unit, unit_ids)
    staff = _name_lookup(session, Staff, staff_ids)
    rooms = _name_lookup(session, Room, room_ids)

    def empty_row() -> dict[str, str]:
        return {key: "" for key in TIMETABLING_TABLE_KEYS}

    for bid in sorted(set(before) | set(after)):
        b_state = before.get(bid)
        a_state = after.get(bid)
        row = empty_row()

        if b_state is None and a_state is not None:
            row["id"] = _card_id_str(a_state)
            row["group"] = courses.get(a_state.get("course_id"), "")
            row["class"] = units.get(a_state.get("unit_id"), "")
            lec = staff.get(a_state.get("staff_id"), "")
            row["lecturer_change"] = lec if lec and lec != "—" else ""
            row["time_change"] = (
                f"{_slot_to_str(a_state['start_slot'])}–{_slot_to_str(a_state['end_slot'])}"
            )
            row["day_change"] = DAYS[a_state["day"]]
            rm = rooms.get(a_state.get("room_id"), "")
            row["room_change"] = rm if rm and rm != "—" else ""
            rows_out.append(row)
            continue

        if b_state is not None and a_state is None:
            row["id"] = _card_id_str(b_state)
            row["group"] = courses.get(b_state.get("course_id"), "")
            row["class"] = units.get(b_state.get("unit_id"), "")
            lec = staff.get(b_state.get("staff_id"), "")
            row["lecturer_change"] = lec if lec and lec != "—" else ""
            row["time_change"] = (
                f"{_slot_to_str(b_state['start_slot'])}–{_slot_to_str(b_state['end_slot'])}"
            )
            row["day_change"] = DAYS[b_state["day"]]
            rm = rooms.get(b_state.get("room_id"), "")
            row["room_change"] = rm if rm and rm != "—" else ""
            row["delete"] = "Y"
            rows_out.append(row)
            continue

        if b_state == a_state or not (b_state and a_state):
            continue

        cid_b = _card_id_str(b_state)
        cid_a = _card_id_str(a_state)
        if cid_b != cid_a:
            if cid_b and cid_a:
                row["id"] = f"{cid_b} → {cid_a}"
            elif cid_a:
                row["id"] = cid_a
        else:
            row["id"] = cid_a

        row["group"] = (
            f"{courses.get(b_state['course_id'], '?')} → {courses.get(a_state['course_id'], '?')}"
            if b_state["course_id"] != a_state["course_id"]
            else courses.get(a_state["course_id"], "")
        )
        row["class"] = (
            f"{units.get(b_state['unit_id'], '—')} → {units.get(a_state['unit_id'], '—')}"
            if b_state["unit_id"] != a_state["unit_id"]
            else units.get(a_state["unit_id"], "")
        )
        if b_state["staff_id"] != a_state["staff_id"]:
            row["lecturer_change"] = (
                f"{staff.get(b_state['staff_id'], '—')} → {staff.get(a_state['staff_id'], '—')}"
            )
        if (b_state["start_slot"], b_state["end_slot"]) != (
            a_state["start_slot"],
            a_state["end_slot"],
        ):
            row["time_change"] = (
                f"{_slot_to_str(b_state['start_slot'])}–{_slot_to_str(b_state['end_slot'])}"
                f" → {_slot_to_str(a_state['start_slot'])}–{_slot_to_str(a_state['end_slot'])}"
            )
        if b_state["day"] != a_state["day"]:
            row["day_change"] = f"{DAYS[b_state['day']]} → {DAYS[a_state['day']]}"
        if b_state["room_id"] != a_state["room_id"]:
            row["room_change"] = (
                f"{rooms.get(b_state['room_id'], '—')} → {rooms.get(a_state['room_id'], '—')}"
            )
        extra: list[str] = []
        if b_state.get("notes") != a_state.get("notes"):
            extra.append("note")
        if b_state.get("in_term_1") != a_state.get("in_term_1") or b_state.get(
            "in_term_2"
        ) != a_state.get("in_term_2"):
            extra.append(
                f"T1/T2 {b_state.get('in_term_1')}/{b_state.get('in_term_2')}"
                f" → {a_state.get('in_term_1')}/{a_state.get('in_term_2')}"
            )
        if b_state.get("online_student_count") != a_state.get("online_student_count"):
            extra.append(
                f"online students {b_state.get('online_student_count')!s}"
                f" → {a_state.get('online_student_count')!s}"
            )
        if extra:
            join_extra = " · ".join(extra)
            row["time_change"] = (
                f"{row['time_change']}{' · ' if row['time_change'] else ''}{join_extra}"
            )

        if any(row[key] for key in TIMETABLING_TABLE_KEYS if key != "id"):
            rows_out.append(row)

    return rows_out

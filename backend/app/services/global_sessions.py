"""Global sessions: group timetable sessions and aggregate entity views."""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from timetable.core.models import Booking, Course, Qualification, Room, Semester, Staff, Unit, Week
from timetable.core.tenancy_models import GlobalSession, GlobalSessionMember, TimetableSession

from .class_custodians import class_custodians_for_session, qualification_names_by_unit
from .qualification_stages import family_title
from .tutorial.lifecycle import is_tutorial_sandbox
from .timetable_grid import get_repeating_week


def normalize_staff_name(name: str | None) -> str:
    return (name or "").strip().casefold()


def _normalize_label(name: str | None) -> str:
    return (name or "").strip().casefold()


def _uniq_sorted_session_names(members: list[dict]) -> list[str]:
    return sorted(
        {str(m["session_name"]) for m in members if m.get("session_name")},
        key=str.casefold,
    )


def _sum_int_field(members: list[dict], field: str) -> int:
    """Sum a numeric field across amalgamated session members (e.g. group counts)."""
    total = 0
    for m in members:
        v = m.get(field)
        if v is None:
            continue
        total += int(v)
    return total


def _merge_field(members: list[dict], field: str):
    """Return the shared value, or ``\"Varies\"`` when members disagree."""
    vals: list = []
    for m in members:
        if field not in m:
            continue
        v = m[field]
        if v is None:
            continue
        vals.append(v)
    if not vals:
        return None
    first = vals[0]
    if all(v == first for v in vals):
        return first
    return "Varies"


def _amalgamate(
    flat_rows: list[dict],
    *,
    key_fn,
    label_field: str,
    enrich: Callable[[list[dict]], dict] | None = None,
) -> list[dict]:
    """Collapse per-session rows that share the same logical entity (by *key_fn*)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in flat_rows:
        key = key_fn(row)
        if not key:
            continue
        groups[key].append(row)

    out: list[dict] = []
    for members in groups.values():
        members.sort(key=lambda m: (m.get("session_name") or "").lower())
        label = (members[0].get(label_field) or "").strip() or members[0].get(label_field)
        session_names = _uniq_sorted_session_names(members)
        entry: dict = {
            label_field: label,
            "session_names": session_names,
            "session_count": len(session_names),
            "members": [
                {
                    "session_id": m["session_id"],
                    "session_name": m["session_name"],
                    "entity_id": m.get("id"),
                }
                for m in members
            ],
        }
        if enrich is not None:
            entry.update(enrich(members))
        out.append(entry)
    out.sort(key=lambda r: (str(r.get(label_field) or "")).lower())
    return out


def global_session_for_timetable(db: Session, timetable_session_id: int) -> GlobalSession | None:
    member = (
        db.query(GlobalSessionMember)
        .options(joinedload(GlobalSessionMember.global_session))
        .filter(GlobalSessionMember.timetable_session_id == timetable_session_id)
        .first()
    )
    return member.global_session if member else None


def linked_timetable_session_ids(db: Session, timetable_session_id: int) -> list[int]:
    """Other member sessions in the same global group (excludes *timetable_session_id*)."""
    gs = global_session_for_timetable(db, timetable_session_id)
    if gs is None:
        return []
    return [
        m.timetable_session_id
        for m in db.query(GlobalSessionMember)
        .filter(
            GlobalSessionMember.global_session_id == gs.id,
            GlobalSessionMember.timetable_session_id != timetable_session_id,
        )
        .all()
    ]


def assert_global_in_org(db: Session, global_session_id: int, org_id: int) -> GlobalSession:
    row = (
        db.query(GlobalSession)
        .filter(
            GlobalSession.id == global_session_id,
            GlobalSession.organization_id == org_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Global session not found")
    return row


def member_session_ids(db: Session, global_session_id: int) -> list[int]:
    return [
        m.timetable_session_id
        for m in db.query(GlobalSessionMember)
        .filter(GlobalSessionMember.global_session_id == global_session_id)
        .order_by(GlobalSessionMember.id)
        .all()
    ]


def set_global_members(
    db: Session,
    *,
    global_session: GlobalSession,
    timetable_session_ids: list[int],
) -> list[int]:
    """Replace linked timetable sessions; each session may belong to at most one global group."""
    org_id = global_session.organization_id
    ids = list(dict.fromkeys(int(x) for x in timetable_session_ids))
    for sid in ids:
        ts = (
            db.query(TimetableSession)
            .filter(TimetableSession.id == sid, TimetableSession.organization_id == org_id)
            .first()
        )
        if ts is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Timetable session {sid} not found in this organization",
            )
        other = (
            db.query(GlobalSessionMember)
            .filter(
                GlobalSessionMember.timetable_session_id == sid,
                GlobalSessionMember.global_session_id != global_session.id,
            )
            .first()
        )
        # A sandbox belongs in its owner's tutorial group and nowhere else. The
        # tutorials write real cover-log entries and calendar weeks, so letting
        # one join a working group would put practice data in the records the
        # timetable team relies on.
        if is_tutorial_sandbox(ts) != bool(global_session.is_tutorial):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{ts.name!r} is a tutorial sandbox and can only belong to a "
                    "tutorial group"
                    if is_tutorial_sandbox(ts)
                    else f"{ts.name!r} is a real timetable and cannot join a tutorial group"
                ),
            )
        if other is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session {ts.name!r} is already linked to another global session",
            )

    db.query(GlobalSessionMember).filter(
        GlobalSessionMember.global_session_id == global_session.id
    ).delete(synchronize_session=False)
    for sid in ids:
        db.add(GlobalSessionMember(global_session_id=global_session.id, timetable_session_id=sid))
    db.flush()
    return ids


def linked_session_busy_slots(
    db: Session,
    *,
    timetable_session_id: int,
    staff_id: int,
) -> tuple[dict[str, list[int]] | None, str | None]:
    """Slots where the same lecturer (by name) is booked in linked sessions."""
    staff = db.get(Staff, staff_id)
    if staff is None or staff.timetable_session_id != timetable_session_id:
        return None, None
    key = normalize_staff_name(staff.name)
    if not key:
        return None, None

    linked_ids = linked_timetable_session_ids(db, timetable_session_id)
    if not linked_ids:
        return None, None

    busy: dict[int, set[int]] = defaultdict(set)
    source_names: list[str] = []

    for sid in linked_ids:
        session = db.get(TimetableSession, sid)
        if session is None:
            continue
        week = get_repeating_week(db, sid)
        if week is None:
            continue
        peers = (
            db.query(Staff)
            .filter(Staff.timetable_session_id == sid)
            .all()
        )
        peer_ids = [p.id for p in peers if normalize_staff_name(p.name) == key]
        if not peer_ids:
            continue
        bookings = (
            db.query(Booking)
            .filter(
                Booking.week_id == week.id,
                Booking.staff_id.in_(peer_ids),
            )
            .all()
        )
        if not bookings:
            continue
        source_names.append(session.name)
        for b in bookings:
            if b.day < 0:
                continue
            for slot in range(b.start_slot, b.end_slot):
                busy[b.day].add(slot)

    if not busy:
        return None, None
    out = {str(day): sorted(slots) for day, slots in busy.items()}
    label = ", ".join(source_names)
    return out, label


def _session_name_map(db: Session, session_ids: list[int]) -> dict[int, str]:
    if not session_ids:
        return {}
    rows = db.query(TimetableSession).filter(TimetableSession.id.in_(session_ids)).all()
    return {r.id: r.name for r in rows}


def aggregated_staff(db: Session, global_session_id: int) -> list[dict]:
    names = _session_name_map(db, member_session_ids(db, global_session_id))
    flat: list[dict] = []
    from timetable.core.staff_hours import (
        classify_staff_variance,
        lecturing_hours_from_fte,
        staff_tab_total_hours,
    )

    from .cover_ledger import cover_hours_by_lecturer, ledger_for
    from .global_staff_hours import staff_hours_snapshot_for_staff_linked

    covered = cover_hours_by_lecturer(db, global_session_id)

    for sid in names:
        for s in (
            db.query(Staff)
            .filter(Staff.timetable_session_id == sid)
            .order_by(Staff.name)
            .all()
        ):
            snap = staff_hours_snapshot_for_staff_linked(db, s)
            lh = lecturing_hours_from_fte(s.fte)
            total = staff_tab_total_hours(s, snap)
            variance = (total - lh) if lh is not None else None
            category = (
                classify_staff_variance(fte=s.fte, lecturing_hours=lh, total_hours=total)
                if lh is not None
                else "unknown"
            )
            flat.append(
                {
                    "id": s.id,
                    "session_id": sid,
                    "session_name": names[sid],
                    "name": s.name,
                    "fte": s.fte,
                    "max_hours_per_week": s.max_hours_per_week,
                    "non_teaching_day": s.non_teaching_day,
                    "total_hours": total,
                    "variance": variance,
                    "variance_category": category,
                }
            )

    def enrich(members: list[dict]) -> dict:
        variance = _merge_field(members, "variance")
        key = normalize_staff_name(members[0].get("name")) if members else ""
        return {
            "fte": _merge_field(members, "fte"),
            "max_hours_per_week": _merge_field(members, "max_hours_per_week"),
            "non_teaching_day": _merge_field(members, "non_teaching_day"),
            "total_hours": _merge_field(members, "total_hours"),
            "variance": variance,
            "member_variances": [m.get("variance") for m in members],
            **ledger_for(variance, covered.get(key, 0.0)),
        }

    return _amalgamate(
        flat,
        key_fn=lambda r: normalize_staff_name(r.get("name")),
        label_field="name",
        enrich=enrich,
    )


def aggregated_rooms(db: Session, global_session_id: int) -> list[dict]:
    names = _session_name_map(db, member_session_ids(db, global_session_id))
    flat: list[dict] = []
    for sid in names:
        for r in (
            db.query(Room)
            .filter(Room.timetable_session_id == sid)
            .order_by(Room.code)
            .all()
        ):
            flat.append(
                {
                    "id": r.id,
                    "session_id": sid,
                    "session_name": names[sid],
                    "code": r.code,
                    "name": r.name,
                    "room_type": r.room_type,
                    "capacity": r.capacity,
                }
            )

    def enrich(members: list[dict]) -> dict:
        return {
            "name": _merge_field(members, "name"),
            "room_type": _merge_field(members, "room_type"),
            "capacity": _merge_field(members, "capacity"),
        }

    return _amalgamate(
        flat,
        key_fn=lambda r: _normalize_label(r.get("code")),
        label_field="code",
        enrich=enrich,
    )


def aggregated_units(db: Session, global_session_id: int) -> list[dict]:
    names = _session_name_map(db, member_session_ids(db, global_session_id))
    flat: list[dict] = []
    for sid in names:
        qual_by_unit = qualification_names_by_unit(db, timetable_session_id=sid)
        for u in (
            db.query(Unit)
            .filter(Unit.timetable_session_id == sid)
            .order_by(Unit.name)
            .all()
        ):
            flat.append(
                {
                    "id": u.id,
                    "session_id": sid,
                    "session_name": names[sid],
                    "name": u.name,
                    "qualifications": qual_by_unit.get(u.id) or "—",
                    "length_slots": u.length_slots,
                    "double_session": getattr(u, "double_session", 0) or 0,
                    "component_codes": u.component_codes,
                }
            )

    def enrich(members: list[dict]) -> dict:
        return {
            "qualifications": _merge_qualification_labels(members),
            "length_slots": _merge_field(members, "length_slots"),
            "double_session": _merge_field(members, "double_session"),
            "component_codes": _merge_field(members, "component_codes"),
        }

    return _amalgamate(
        flat,
        key_fn=lambda r: _normalize_label(r.get("name")),
        label_field="name",
        enrich=enrich,
    )


def aggregated_qualifications(db: Session, global_session_id: int) -> list[dict]:
    names = _session_name_map(db, member_session_ids(db, global_session_id))
    flat: list[dict] = []
    for sid in names:
        rows = (
            db.query(Qualification)
            .filter(Qualification.timetable_session_id == sid)
            .order_by(Qualification.name)
            .all()
        )
        # A split qualification lists under the one name it was split from; its
        # stages are a column, not separate qualifications.
        by_family: dict[int, list[Qualification]] = {}
        for q in rows:
            by_family.setdefault(q.parent_qualification_id or q.id, []).append(q)
        for q in rows:
            family = by_family[q.parent_qualification_id or q.id]
            is_split = len(family) > 1
            flat.append(
                {
                    "id": q.id,
                    "session_id": sid,
                    "session_name": names[sid],
                    "name": family_title(family) if is_split else q.name,
                    "stage_name": q.name if is_split else "",
                    "num_groups": q.num_groups,
                    "schedule_period": q.schedule_period,
                    "delivery_mode": getattr(q, "delivery_mode", "regular"),
                }
            )

    def enrich(members: list[dict]) -> dict:
        stages = sorted({(m.get("stage_name") or "").strip() for m in members} - {""})
        return {
            "stages": ", ".join(stages) if stages else "—",
            "num_groups": _sum_int_field(members, "num_groups"),
            "schedule_period": _merge_field(members, "schedule_period"),
            "delivery_mode": _merge_field(members, "delivery_mode"),
        }

    return _amalgamate(
        flat,
        key_fn=lambda r: _normalize_label(r.get("name")),
        label_field="name",
        enrich=enrich,
    )


def _merge_comma_list(rows: list[dict], field: str) -> str:
    """Union of comma-separated labels across sessions, de-duplicated."""
    parts: list[str] = []
    for row in rows:
        raw = (row.get(field) or "").strip()
        if raw and raw != "—":
            parts.extend(p.strip() for p in raw.split(",") if p.strip())
    if not parts:
        return "—"
    return ", ".join(sorted(set(parts), key=str.casefold))


def _merge_qualification_labels(rows: list[dict]) -> str:
    return _merge_comma_list(rows, "qualifications")


def _merge_custodian_detail(rows: list[dict], field: str) -> str:
    """Combine per-session values; prefix with session when they differ."""
    if not rows:
        return "—"
    values = [(r.get("session_name") or "", (r.get(field) or "—").strip()) for r in rows]
    bare = {v for _, v in values if v and v != "—"}
    if len(bare) == 1:
        return bare.pop()
    if len(bare) == 0:
        return "—"
    return "; ".join(f"{sn}: {val}" for sn, val in values if val and val != "—")


def _split_labels(raw: object) -> list[str]:
    """Comma-joined display labels back into individual names."""
    text = (str(raw or "")).strip()
    if not text or text == "—":
        return []
    out: list[str] = []
    for part in text.split(","):
        # Custodian/lecturer labels can carry a delivery count: "Name (3)".
        name = part.strip()
        if name.endswith(")") and "(" in name:
            name = name[: name.rindex("(")].strip()
        # "Unassigned" is a bucket in the delivery counts, not a person.
        if name and name != "—" and name != "Unassigned":
            out.append(name)
    return out


def set_global_class_custodian(
    db: Session,
    *,
    global_session_id: int,
    unit_name: str,
    staff_name: str | None,
) -> dict:
    """Pin one custodian for a class across every session that teaches it.

    A class taught at two campuses is one class to the curriculum, so the
    workspace pins it once and writes through to each member session. Matching
    is by name, the same way the workspace amalgamates everything else.

    Sessions that teach the class but have nobody of that name are skipped and
    named in the result rather than failing the whole write — a half-applied
    pin the user is told about beats an error that changes nothing.
    """
    wanted_unit = _normalize_label(unit_name)
    if not wanted_unit:
        raise ValueError("A class name is required")
    wanted_staff = normalize_staff_name(staff_name) if staff_name else None

    session_ids = member_session_ids(db, global_session_id)
    names = _session_name_map(db, session_ids)
    applied: list[str] = []
    skipped: list[str] = []

    for sid in session_ids:
        unit = next(
            (
                u
                for u in db.query(Unit).filter(Unit.timetable_session_id == sid).all()
                if _normalize_label(u.name) == wanted_unit
            ),
            None,
        )
        if unit is None:
            continue  # this session does not teach the class at all
        if wanted_staff is None:
            unit.custodian_staff_id = None
            applied.append(names.get(sid, f"Session {sid}"))
            continue
        staff = next(
            (
                s
                for s in db.query(Staff).filter(Staff.timetable_session_id == sid).all()
                if normalize_staff_name(s.name) == wanted_staff
            ),
            None,
        )
        if staff is None:
            skipped.append(names.get(sid, f"Session {sid}"))
            continue
        unit.custodian_staff_id = staff.id
        applied.append(names.get(sid, f"Session {sid}"))

    db.commit()
    return {
        "applied": len(applied),
        "applied_sessions": applied,
        "skipped_sessions": skipped,
    }


def aggregated_class_custodians(db: Session, global_session_id: int) -> dict:
    session_ids = member_session_ids(db, global_session_id)
    names = _session_name_map(db, session_ids)
    flat: list[dict] = []
    for sid in session_ids:
        report = class_custodians_for_session(db, timetable_session_id=sid)
        for row in report.get("rows", []):
            flat.append(
                {
                    **row,
                    "session_id": sid,
                    "session_name": names.get(sid, f"Session {sid}"),
                }
            )

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in flat:
        key = _normalize_label(row.get("unit_name"))
        if key:
            groups[key].append(row)

    amalgamated: list[dict] = []
    for members in groups.values():
        members.sort(key=lambda m: (m.get("session_name") or "").lower())
        session_names = _uniq_sorted_session_names(members)
        amalgamated.append(
            {
                "unit_id": members[0].get("unit_id"),
                "unit_name": (members[0].get("unit_name") or "").strip(),
                "session_names": session_names,
                "session_count": len(session_names),
                "units": _merge_comma_list(members, "units"),
                "qualifications": _merge_qualification_labels(members),
                "lecturers": _merge_custodian_detail(members, "lecturers"),
                "custodian": _merge_custodian_detail(members, "custodian"),
                # A pin in any member session marks the row: the workspace pin
                # writes to all of them, but a session-level pin made earlier
                # should still read as pinned here.
                "custodian_is_manual": any(
                    bool(m.get("custodian_is_manual")) for m in members
                ),
                #: Choices for the row's dropdown, by name — the workspace
                #: matches people by name rather than id. Everyone who delivers
                #: the class anywhere, plus whoever is currently custodian: a
                #: custodian pinned from outside the teaching list must still
                #: appear as its own dropdown's value.
                "custodian_choices": sorted(
                    {
                        name
                        for m in members
                        for name in _split_labels(m.get("lecturers"))
                        + _split_labels(m.get("custodian"))
                    }
                ),
            }
        )
    amalgamated.sort(key=lambda r: (r["unit_name"] or "").lower())

    raw_count = len(flat)
    summary = (
        f"{len(amalgamated)} class(es) amalgamated from {raw_count} row(s) "
        f"across {len(session_ids)} linked session(s)"
    )
    return {"rows": amalgamated, "summary": summary}

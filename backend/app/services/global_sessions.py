"""Global sessions: group timetable sessions and aggregate entity views."""
from __future__ import annotations

from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from timetable.core.models import Booking, Course, Qualification, Room, Semester, Staff, Unit, Week
from timetable.core.tenancy_models import GlobalSession, GlobalSessionMember, TimetableSession

from .class_custodians import class_custodians_for_session
from .timetable_grid import get_repeating_week


def normalize_staff_name(name: str | None) -> str:
    return (name or "").strip().casefold()


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
    rows: list[dict] = []
    for sid in names:
        for s in (
            db.query(Staff)
            .filter(Staff.timetable_session_id == sid)
            .order_by(Staff.name)
            .all()
        ):
            rows.append(
                {
                    "id": s.id,
                    "session_id": sid,
                    "session_name": names[sid],
                    "name": s.name,
                    "fte": s.fte,
                    "max_hours_per_week": s.max_hours_per_week,
                    "non_teaching_day": s.non_teaching_day,
                }
            )
    rows.sort(key=lambda r: (r["name"].lower(), r["session_name"].lower()))
    return rows


def aggregated_rooms(db: Session, global_session_id: int) -> list[dict]:
    names = _session_name_map(db, member_session_ids(db, global_session_id))
    rows: list[dict] = []
    for sid in names:
        for r in (
            db.query(Room)
            .filter(Room.timetable_session_id == sid)
            .order_by(Room.code)
            .all()
        ):
            rows.append(
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
    rows.sort(key=lambda r: (r["code"].lower(), r["session_name"].lower()))
    return rows


def aggregated_units(db: Session, global_session_id: int) -> list[dict]:
    names = _session_name_map(db, member_session_ids(db, global_session_id))
    rows: list[dict] = []
    for sid in names:
        for u in (
            db.query(Unit)
            .filter(Unit.timetable_session_id == sid)
            .order_by(Unit.name)
            .all()
        ):
            rows.append(
                {
                    "id": u.id,
                    "session_id": sid,
                    "session_name": names[sid],
                    "name": u.name,
                    "length_slots": u.length_slots,
                    "double_session": getattr(u, "double_session", 0) or 0,
                    "component_codes": u.component_codes,
                }
            )
    rows.sort(key=lambda r: (r["name"].lower(), r["session_name"].lower()))
    return rows


def aggregated_qualifications(db: Session, global_session_id: int) -> list[dict]:
    names = _session_name_map(db, member_session_ids(db, global_session_id))
    rows: list[dict] = []
    for sid in names:
        for q in (
            db.query(Qualification)
            .filter(Qualification.timetable_session_id == sid)
            .order_by(Qualification.name)
            .all()
        ):
            rows.append(
                {
                    "id": q.id,
                    "session_id": sid,
                    "session_name": names[sid],
                    "name": q.name,
                    "num_groups": q.num_groups,
                    "schedule_period": q.schedule_period,
                    "delivery_mode": getattr(q, "delivery_mode", "regular"),
                }
            )
    rows.sort(key=lambda r: (r["name"].lower(), r["session_name"].lower()))
    return rows


def aggregated_class_custodians(db: Session, global_session_id: int) -> dict:
    session_ids = member_session_ids(db, global_session_id)
    names = _session_name_map(db, session_ids)
    all_rows: list[dict] = []
    for sid in session_ids:
        report = class_custodians_for_session(db, timetable_session_id=sid)
        for row in report.get("rows", []):
            all_rows.append(
                {
                    **row,
                    "session_id": sid,
                    "session_name": names.get(sid, f"Session {sid}"),
                }
            )
    all_rows.sort(key=lambda r: (r["unit_name"].lower(), r["session_name"].lower()))
    summary = f"{len(all_rows)} class row(s) across {len(session_ids)} linked session(s)"
    return {"rows": all_rows, "summary": summary}

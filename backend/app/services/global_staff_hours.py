"""Staff hours across linked global sessions (same lecturer name)."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session, joinedload

from timetable.core.models import (
    Booking,
    Qualification,
    Semester,
    Staff,
    StaffQualificationOnlineStudents,
    StaffUnitOnlineStudents,
    Unit,
    Week,
)
from timetable.core.staff_hours import (
    StaffHoursSnapshot,
    load_qualification_online_student_totals,
    load_unit_online_student_totals,
    load_unit_qualification_ids,
    resolve_default_online_students_per_class,
    staff_hours_snapshot_for_bookings,
)


def _normalize_staff_name(name: str | None) -> str:
    from .global_sessions import normalize_staff_name

    return normalize_staff_name(name)


def _global_session_for_timetable(db: Session, timetable_session_id: int):
    from .global_sessions import global_session_for_timetable

    return global_session_for_timetable(db, timetable_session_id)


def _member_session_ids(db: Session, global_session_id: int) -> list[int]:
    from .global_sessions import member_session_ids

    return member_session_ids(db, global_session_id)


STAFF_HOURS_PROFILE_FIELDS = (
    "cost_centre",
    "fte",
    "max_hours_per_week",
    "non_teaching_day",
    "ot_hours",
    "development_project_hours",
    "development_project_description",
    "tae_hours",
    "supervision_hours",
    "default_online_students_per_class",
)


def linked_session_ids_for_staff(db: Session, staff: Staff) -> list[int] | None:
    gs = _global_session_for_timetable(db, staff.timetable_session_id)
    if gs is None:
        return None
    return _member_session_ids(db, gs.id)


def linked_peer_staff(db: Session, staff: Staff) -> list[Staff]:
    """All staff rows with the same name in the global group (including *staff*)."""
    session_ids = linked_session_ids_for_staff(db, staff)
    if not session_ids:
        return [staff]
    key = _normalize_staff_name(staff.name)
    if not key:
        return [staff]
    peers: list[Staff] = []
    for sid in session_ids:
        for row in db.query(Staff).filter(Staff.timetable_session_id == sid).all():
            if _normalize_staff_name(row.name) == key:
                peers.append(row)
    return peers or [staff]


def linked_peer_staff_ids(db: Session, staff: Staff) -> list[int]:
    return [p.id for p in linked_peer_staff(db, staff)]


def copy_staff_hours_profile(*, source: Staff, target: Staff) -> None:
    for field in STAFF_HOURS_PROFILE_FIELDS:
        setattr(target, field, getattr(source, field))


def propagate_staff_hours_profile(db: Session, canonical: Staff) -> None:
    """Copy spreadsheet-style hour fields from *canonical* to every linked peer."""
    for peer in linked_peer_staff(db, canonical):
        if peer.id == canonical.id:
            continue
        copy_staff_hours_profile(source=canonical, target=peer)


def _qual_id_by_name(db: Session, timetable_session_id: int) -> dict[str, int]:
    return {
        _normalize_staff_name(q.name): q.id
        for q in db.query(Qualification)
        .filter(Qualification.timetable_session_id == timetable_session_id)
        .all()
        if _normalize_staff_name(q.name)
    }


def _unit_id_by_name(db: Session, timetable_session_id: int) -> dict[str, int]:
    return {
        _normalize_staff_name(u.name): u.id
        for u in db.query(Unit).filter(Unit.timetable_session_id == timetable_session_id).all()
        if _normalize_staff_name(u.name)
    }


def copy_staff_online_overrides(
    db: Session,
    *,
    source_staff_id: int,
    source_session_id: int,
    target_staff_id: int,
    target_session_id: int,
) -> None:
    """Copy per-qual / per-class online cohort overrides, matching by name in the target session."""
    src_qual = _qual_id_by_name(db, source_session_id)
    tgt_qual = _qual_id_by_name(db, target_session_id)
    src_unit = _unit_id_by_name(db, source_session_id)
    tgt_unit = _unit_id_by_name(db, target_session_id)

    db.query(StaffQualificationOnlineStudents).filter(
        StaffQualificationOnlineStudents.staff_id == target_staff_id
    ).delete(synchronize_session=False)
    db.query(StaffUnitOnlineStudents).filter(
        StaffUnitOnlineStudents.staff_id == target_staff_id
    ).delete(synchronize_session=False)

    for row in (
        db.query(StaffQualificationOnlineStudents)
        .filter(StaffQualificationOnlineStudents.staff_id == source_staff_id)
        .all()
    ):
        src_q = db.get(Qualification, row.qualification_id)
        if src_q is None:
            continue
        key = _normalize_staff_name(src_q.name)
        tgt_id = tgt_qual.get(key)
        if tgt_id is None:
            continue
        db.add(
            StaffQualificationOnlineStudents(
                staff_id=target_staff_id,
                qualification_id=tgt_id,
                student_count=row.student_count,
            )
        )

    for row in (
        db.query(StaffUnitOnlineStudents)
        .filter(StaffUnitOnlineStudents.staff_id == source_staff_id)
        .all()
    ):
        src_u = db.get(Unit, row.unit_id)
        if src_u is None:
            continue
        key = _normalize_staff_name(src_u.name)
        tgt_id = tgt_unit.get(key)
        if tgt_id is None:
            continue
        db.add(
            StaffUnitOnlineStudents(
                staff_id=target_staff_id,
                unit_id=tgt_id,
                student_count=row.student_count,
            )
        )


def propagate_staff_online_overrides(db: Session, canonical: Staff) -> None:
    """Replicate online cohort overrides from *canonical* onto each linked peer."""
    for peer in linked_peer_staff(db, canonical):
        if peer.id == canonical.id:
            continue
        copy_staff_online_overrides(
            db,
            source_staff_id=canonical.id,
            source_session_id=canonical.timetable_session_id,
            target_staff_id=peer.id,
            target_session_id=peer.timetable_session_id,
        )


def _merged_online_student_totals(
    db: Session,
    *,
    peers: list[Staff],
    bookings: list[Booking],
) -> tuple[dict[int, int | None], dict[int, int | None]]:
    """Map unit/qual ids from linked bookings to cohort overrides matched by entity name."""
    qual_by_name: dict[str, int | None] = {}
    unit_by_name: dict[str, int | None] = {}
    for peer in peers:
        for qid, count in load_qualification_online_student_totals(db, peer.id).items():
            qual = db.get(Qualification, qid)
            if qual is None:
                continue
            key = _normalize_staff_name(qual.name)
            if key:
                qual_by_name[key] = count
        for uid, count in load_unit_online_student_totals(db, peer.id).items():
            unit = db.get(Unit, uid)
            if unit is None:
                continue
            key = _normalize_staff_name(unit.name)
            if key:
                unit_by_name[key] = count

    unit_qual_ids = load_unit_qualification_ids(db)
    qual_totals: dict[int, int | None] = {}
    unit_totals: dict[int, int | None] = {}
    seen_qual_ids: set[int] = set()
    for booking in bookings:
        if booking.unit_id is None:
            continue
        unit = db.get(Unit, booking.unit_id)
        if unit is not None:
            key = _normalize_staff_name(unit.name)
            if key in unit_by_name:
                unit_totals[booking.unit_id] = unit_by_name[key]
        for qid in unit_qual_ids.get(booking.unit_id, []):
            seen_qual_ids.add(qid)
    for qid in seen_qual_ids:
        qual = db.get(Qualification, qid)
        if qual is None:
            continue
        key = _normalize_staff_name(qual.name)
        if key in qual_by_name:
            qual_totals[qid] = qual_by_name[key]
    return qual_totals, unit_totals


def bookings_for_linked_staff(db: Session, staff: Staff) -> list[Booking]:
    """Bookings for this lecturer across all linked sessions (matched by name)."""
    session_ids = linked_session_ids_for_staff(db, staff)
    peer_ids = linked_peer_staff_ids(db, staff)
    if not session_ids or not peer_ids:
        return (
            db.query(Booking)
            .options(
                joinedload(Booking.room),
                joinedload(Booking.unit),
                joinedload(Booking.course),
            )
            .filter(Booking.staff_id == staff.id)
            .all()
        )

    week_ids = [
        int(wid)
        for (wid,) in db.query(Week.id)
        .join(Semester, Week.semester_id == Semester.id)
        .filter(Semester.timetable_session_id.in_(session_ids))
        .all()
    ]
    if not week_ids:
        return []

    from timetable.core.booking_staff import timetable_staff_ids

    peer_set = set(peer_ids)
    rows = (
        db.query(Booking)
        .options(
            joinedload(Booking.room),
            joinedload(Booking.unit),
            joinedload(Booking.course),
        )
        .filter(Booking.week_id.in_(week_ids))
        .all()
    )
    return [b for b in rows if peer_set.intersection(timetable_staff_ids(b))]


def staff_hours_snapshot_for_staff_linked(db: Session, staff: Staff) -> StaffHoursSnapshot:
    """Hours snapshot including timetabled load from every linked session copy of this lecturer."""
    bookings = bookings_for_linked_staff(db, staff)
    peers = linked_peer_staff(db, staff)
    return _hours_snapshot_for_staff_with_bookings(db, staff, peers, bookings)


def _hours_snapshot_for_staff_with_bookings(
    db: Session,
    staff: Staff,
    peers: list[Staff],
    bookings: list[Booking],
) -> StaffHoursSnapshot:
    unit_qual_ids = load_unit_qualification_ids(db)
    qual_student_totals, unit_student_totals = _merged_online_student_totals(
        db,
        peers=peers,
        bookings=bookings,
    )
    legacy_default = resolve_default_online_students_per_class(staff)
    return staff_hours_snapshot_for_bookings(
        bookings,
        staff_id=None,
        unit_qual_ids=unit_qual_ids,
        qual_student_totals=qual_student_totals,
        unit_student_totals=unit_student_totals,
        legacy_default_per_class=legacy_default,
    )


def staff_tab_total_hours_map_for_session(
    db: Session,
    timetable_session_id: int,
    *,
    staff_rows: list[Staff] | None = None,
) -> dict[int, float]:
    """Batch Staff-tab totals for one session (sidebar labels).

    Computes hours in one pass instead of reloading all bookings per lecturer.
    """
    from timetable.core.staff_hours import (
        staff_tab_total_hours,
        staff_tab_total_hours_by_staff_id,
    )
    from timetable.core.sidebar_order import ordered_staff

    if staff_rows is None:
        staff_rows = [s for s in ordered_staff(db) if s.timetable_session_id == timetable_session_id]
    if not staff_rows:
        return {}

    if _global_session_for_timetable(db, timetable_session_id) is None:
        try:
            all_totals = staff_tab_total_hours_by_staff_id(db)
        except Exception:
            return {s.id: 0.0 for s in staff_rows}
        return {s.id: all_totals.get(s.id, 0.0) for s in staff_rows}

    gs = _global_session_for_timetable(db, timetable_session_id)
    if gs is None:
        return {s.id: 0.0 for s in staff_rows}
    session_ids = _member_session_ids(db, gs.id)
    if not session_ids:
        return {s.id: 0.0 for s in staff_rows}

    week_ids = [
        int(wid)
        for (wid,) in db.query(Week.id)
        .join(Semester, Week.semester_id == Semester.id)
        .filter(Semester.timetable_session_id.in_(session_ids))
        .all()
    ]
    all_bookings: list[Booking] = []
    if week_ids:
        all_bookings = (
            db.query(Booking)
            .options(
                joinedload(Booking.room),
                joinedload(Booking.unit),
                joinedload(Booking.course),
            )
            .filter(Booking.week_id.in_(week_ids))
            .all()
        )

    from timetable.core.booking_staff import timetable_staff_ids

    bookings_by_staff: dict[int, list[Booking]] = defaultdict(list)
    seen_for_staff: dict[int, set[int]] = defaultdict(set)
    for booking in all_bookings:
        bid = booking.id
        for sid in timetable_staff_ids(booking):
            if bid in seen_for_staff[sid]:
                continue
            seen_for_staff[sid].add(bid)
            bookings_by_staff[sid].append(booking)

    all_peers = db.query(Staff).filter(Staff.timetable_session_id.in_(session_ids)).all()
    peers_by_name: dict[str, list[Staff]] = defaultdict(list)
    for peer in all_peers:
        key = _normalize_staff_name(peer.name)
        if key:
            peers_by_name[key].append(peer)

    out: dict[int, float] = {}
    for staff in staff_rows:
        key = _normalize_staff_name(staff.name)
        peers = peers_by_name.get(key, [staff])
        peer_ids = {p.id for p in peers}
        merged: list[Booking] = []
        seen_booking: set[int] = set()
        for peer_id in peer_ids:
            for booking in bookings_by_staff.get(peer_id, []):
                if booking.id in seen_booking:
                    continue
                seen_booking.add(booking.id)
                merged.append(booking)
        snap = _hours_snapshot_for_staff_with_bookings(db, staff, peers, merged)
        out[staff.id] = staff_tab_total_hours(staff, snap)
    return out


def staff_tab_total_hours_for_staff(db: Session, staff: Staff) -> float:
    """Staff-tab total hours, including bookings from all linked sessions when applicable."""
    totals = staff_tab_total_hours_map_for_session(
        db,
        staff.timetable_session_id,
        staff_rows=[staff],
    )
    return totals.get(staff.id, 0.0)


def staff_hours_snapshot_for_staff(db: Session, staff: Staff) -> StaffHoursSnapshot:
    """Use linked global hours when this session is in a global group."""
    if linked_session_ids_for_staff(db, staff) is None:
        from timetable.core.staff_hours import staff_hours_snapshots_by_staff_id

        snap_map = staff_hours_snapshots_by_staff_id(db)
        return snap_map.get(staff.id) or staff_hours_snapshot_for_bookings([], staff_id=staff.id)
    return staff_hours_snapshot_for_staff_linked(db, staff)

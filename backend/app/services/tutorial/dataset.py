"""Deterministic synthetic dataset for the in-app tutorial sandbox.

Hand-authored fixed literals (no RNG) in the exact ``serialize_session`` payload
format, so ``restore_session`` can apply it and ``tutorial-reset`` can re-apply
it byte-for-byte. Local ids are 1..n; restore remaps them to fresh ids.

The data is a small "Coastal TAFE" semester with deliberate teaching traps,
each targeted by one tutorial module:

- Tom Nguyen double-booked on Monday            -> staff_double_booking (M4)
- Linux Admin (needs on-campus) in ONL-1        -> room_type            (M4)
- First Aid (needs 25 seats) in 12-seat A1.10   -> room_capacity        (M4)
- David Chen teaching outside his competencies  -> lecturer_not_allowed (M4)
- Marcus Webb (Mon-Wed only) booked Thursday    -> staff_unavailable    (M5)
- Priya Sharma over her 10.5h weekly cap        -> staff_hour_cap x2    (M5)
- CYB-A "Cyber Threat Intelligence" unplaced    -> holding area target  (M3)
- CYB-T mostly unscheduled (incl. double-session pair) -> capstone      (M7)

Slots are half-hours from 08:00 (slot 4 = 10:00). Days 0=Mon .. 4=Fri.
"""
from __future__ import annotations

from typing import Any

from timetable.core.clash_check_settings import (
    clash_check_settings_to_json,
    default_clash_check_enabled,
)
from timetable.io.backup_payload import PAYLOAD_VERSION

# Soft "ideal timetable" scheduling rules that fire on almost any realistic
# dataset. The tutorial disables them per-session so the Warnings tab shows
# exactly the violations the modules teach. Hard scheduling rules stay on.
TUTORIAL_DISABLED_CLASH_CODES: tuple[str, ...] = (
    "monday_start_before_930",
    "staff_idle_gap_over_2h",
    "staff_daily_hours_below_5",
    "staff_daily_hours_above_9",
    "student_daily_hours_below_5",
    "student_daily_hours_above_8",
    "student_idle_gap_over_2h",
)

# The exact violation multiset the pristine dataset must produce after the
# tutorial clash settings are applied. Tests assert this so the data can't
# silently drift.
EXPECTED_VIOLATION_CODES: dict[str, int] = {
    "staff_double_booking": 1,   # Tom Nguyen, Monday
    "room_type": 1,              # Linux Admin (CYB-B) in ONL-1
    "room_capacity": 1,          # First Aid in A1.10
    "staff_unavailable": 1,      # Marcus Webb, Thursday
    "lecturer_not_allowed": 1,   # David Chen on Secure Programming
    "staff_hour_cap": 2,         # Priya Sharma, T1 and T2
}

# Unplaced (course code -> unit names) the holding area must show pristine.
EXPECTED_HOLDING: dict[str, list[str]] = {
    "CYB-A": ["Cyber Threat Intelligence — VU23223"],
    "CYB-T": [
        "Network Security Fundamentals — VU23217",
        "Cyber Incident Response — VU23221",   # session part 1
        "Cyber Incident Response — VU23221",   # session part 2
        "Workplace Communication — BSBXCM301",
    ],
}


def tutorial_clash_settings_json() -> str:
    """Per-session clash settings JSON with the noisy soft rules disabled."""
    settings = default_clash_check_enabled()
    for code in TUTORIAL_DISABLED_CLASH_CODES:
        if code in settings:
            settings[code] = False
    return clash_check_settings_to_json(settings)


def _qual(qid: int, name: str, num_groups: int) -> dict[str, Any]:
    return {
        "id": qid,
        "name": name,
        "num_groups": num_groups,
        "schedule_period": "day",
        "delivery_mode": "regular",
        "block_week_count": None,
        "block_start_semester_week": None,
    }


def _course(cid: int, code: str, name: str, qual_id: int, order: int) -> dict[str, Any]:
    return {
        "id": cid,
        "code": code,
        "name": name,
        "qualification_id": qual_id,
        "timetable_locked": 0,
        "sidebar_order": order,
        "block_week_count": None,
        "block_start_semester_week": None,
        "is_block_cohort": 0,
    }


def _unit(
    uid: int,
    name: str,
    length_slots: int,
    *,
    codes: str | None = None,
    room_type: str | None = None,
    capacity: int | None = None,
    double: bool = False,
) -> dict[str, Any]:
    return {
        "id": uid,
        "name": name,
        "length_slots": length_slots,
        "component_codes": codes,
        "required_room_type": room_type,
        "required_capacity": capacity,
        "double_session": 1 if double else 0,
        "double_session_same_day": None,
        "double_session_first_slots": length_slots // 2 if double else None,
    }


def _staff(
    sid: int,
    name: str,
    *,
    fte: float | None,
    cap: float | None = None,
    non_teaching_day: int | None = None,
    cost_centre: str = "IT & Cyber Security",
    order: int = 0,
) -> dict[str, Any]:
    return {
        "id": sid,
        "name": name,
        "cost_centre": cost_centre,
        "max_hours_per_week": cap,
        "non_teaching_day": non_teaching_day,
        "fte": fte,
        "ot_hours": None,
        "development_project_hours": None,
        "development_project_description": None,
        "tae_hours": None,
        "supervision_hours": None,
        "default_online_students_per_class": None,
        "timetable_locked": 0,
        "sidebar_order": order,
    }


def _room(rid: int, code: str, name: str, room_type: str, capacity: int) -> dict[str, Any]:
    return {"id": rid, "code": code, "name": name, "room_type": room_type, "capacity": capacity}


def _booking(
    bid: int,
    course: int,
    unit: int,
    staff: int | None,
    room: int | None,
    day: int,
    start: int,
    end: int,
    *,
    part: int = 1,
    lock_time: int = 0,
) -> dict[str, Any]:
    return {
        "id": bid,
        "course_id": course,
        "unit_id": unit,
        "staff_id": staff,
        "sfs_co_teacher_staff_id": None,
        "sfs_co_teacher_in_term_1": 0,
        "sfs_co_teacher_in_term_2": 0,
        "cover_staff_id": None,
        "room_id": room,
        "day": day,
        "start_slot": start,
        "end_slot": end,
        "notes": None,
        "external_id": None,
        "in_term_1": 1,
        "in_term_2": 1,
        "online_student_count": None,
        "lock_time": lock_time,
        "lock_staff": 0,
        "session_part": part,
        "session_weeks": None,
        "block_week_index": None,
        "combined_class_group_id": None,
    }


# Local-id aliases used below so the booking matrix reads like a timetable.
Q_CYBER, Q_COMMUNITY = 1, 2
CYB_A, CYB_B, CHC_A, CYB_T = 1, 2, 3, 4
(U_NETSEC, U_THREAT, U_SECPROG, U_LINUX, U_INCIDENT, U_WEBSEC,
 U_WORKCOM, U_FIRSTAID, U_CASEMGMT, U_LEGAL, U_COUNSEL, U_DIGLIT) = range(1, 13)
(S_PRIYA, S_TOM, S_MARCUS, S_DAVID, S_JAMES, S_ELENA, S_SARAH, S_AISHA) = range(1, 9)
(R_B104, R_B105, R_A201, R_A202, R_A110, R_W101, R_ONL1) = range(1, 8)


def build_tutorial_payload() -> dict[str, Any]:
    """Fresh copy of the tutorial dataset in restore_session payload format."""
    return {
        "version": PAYLOAD_VERSION,
        "qualifications": [
            _qual(Q_CYBER, "Certificate IV in Cyber Security — 22603VIC", 3),
            _qual(Q_COMMUNITY, "Diploma of Community Services — CHC52021", 1),
        ],
        "qualification_time_windows": [],
        "courses": [
            _course(CYB_A, "CYB-A", "Cyber Security Group A", Q_CYBER, 0),
            _course(CYB_B, "CYB-B", "Cyber Security Group B", Q_CYBER, 1),
            _course(CHC_A, "CHC-A", "Community Services Group A", Q_COMMUNITY, 2),
            _course(CYB_T, "CYB-T", "Cyber Security capstone group", Q_CYBER, 3),
        ],
        "units": [
            _unit(U_NETSEC, "Network Security Fundamentals — VU23217", 4, codes="VU23217"),
            _unit(U_THREAT, "Cyber Threat Intelligence — VU23223", 4, codes="VU23223"),
            _unit(U_SECPROG, "Secure Programming Basics — VU23225", 6, codes="VU23225"),
            _unit(
                U_LINUX,
                "Linux Administration — ICTSAS432",
                4,
                codes="ICTSAS432",
                room_type="on-campus",
            ),
            _unit(
                U_INCIDENT,
                "Cyber Incident Response — VU23221",
                8,
                codes="VU23221",
                double=True,
            ),
            _unit(
                U_WEBSEC,
                "Interactive Web Security — VU23218",
                4,
                codes="VU23218, VU23219",
            ),
            _unit(U_WORKCOM, "Workplace Communication — BSBXCM301", 4, codes="BSBXCM301"),
            _unit(
                U_FIRSTAID,
                "Provide First Aid — HLTAID011",
                8,
                codes="HLTAID011",
                capacity=25,
            ),
            _unit(U_CASEMGMT, "Case Management Skills — CHCCSM013", 4, codes="CHCCSM013"),
            _unit(U_LEGAL, "Legal and Ethical Practice — CHCLEG003", 4, codes="CHCLEG003"),
            _unit(U_COUNSEL, "Counselling Foundations — CHCCSL001", 6, codes="CHCCSL001"),
            _unit(
                U_DIGLIT,
                "Digital Literacy Support — BSBTEC201",
                4,
                codes="BSBTEC201",
                room_type="online",
            ),
        ],
        "unit_qualifications": [
            {"unit_id": u, "qualification_id": Q_CYBER}
            for u in (U_NETSEC, U_THREAT, U_SECPROG, U_LINUX, U_INCIDENT, U_WEBSEC, U_WORKCOM)
        ]
        + [
            {"unit_id": u, "qualification_id": Q_COMMUNITY}
            for u in (U_FIRSTAID, U_CASEMGMT, U_LEGAL, U_COUNSEL, U_DIGLIT)
        ],
        "unit_allowed_rooms": [],
        "course_units": [],
        "staff": [
            _staff(S_PRIYA, "Priya Sharma", fte=0.5, cap=10.5, order=0),
            _staff(S_TOM, "Tom Nguyen", fte=1.0, order=1),
            _staff(S_MARCUS, "Marcus Webb", fte=0.6, order=2),
            _staff(S_DAVID, "David Chen", fte=0.8, order=3),
            _staff(S_JAMES, "James Taylor", fte=1.0, order=4),
            _staff(
                S_ELENA,
                "Elena Rodriguez",
                fte=1.0,
                non_teaching_day=4,
                cost_centre="Community Services",
                order=5,
            ),
            _staff(S_SARAH, "Sarah O'Brien", fte=0.5, cost_centre="Community Services", order=6),
            _staff(S_AISHA, "Aisha Khan", fte=0.4, order=7),
        ],
        "staff_qualification_online_students": [],
        "staff_unit_online_students": [],
        "staff_preferences": [],
        # Allowed-lecturer lists. Every booked lecturer is on their unit's list
        # EXCEPT David Chen on Secure Programming (the M4 soft violation).
        # James Taylor is on every list — the tutorial's reassignment target.
        "staff_competencies": [
            {"staff_id": s, "unit_id": u}
            for u, staff_ids in {
                U_NETSEC: (S_TOM, S_JAMES),
                U_THREAT: (S_TOM, S_JAMES),
                U_SECPROG: (S_PRIYA, S_JAMES),          # David deliberately absent
                U_LINUX: (S_MARCUS, S_TOM, S_JAMES),
                U_INCIDENT: (S_TOM, S_PRIYA, S_JAMES),
                U_WEBSEC: (S_AISHA, S_JAMES),
                U_WORKCOM: (S_ELENA, S_JAMES),          # M2 adds the user's new staff here
                U_FIRSTAID: (S_SARAH, S_JAMES),
                U_CASEMGMT: (S_MARCUS, S_ELENA, S_JAMES),
                U_LEGAL: (S_ELENA, S_JAMES),
                U_COUNSEL: (S_SARAH, S_JAMES),
                U_DIGLIT: (S_PRIYA, S_JAMES),
            }.items()
            for s in staff_ids
        ],
        # Marcus Webb works Monday-Wednesday only (full days).
        "staff_availability": [
            {"id": 1, "staff_id": S_MARCUS, "day": 0, "start_slot": 0, "end_slot": 28},
            {"id": 2, "staff_id": S_MARCUS, "day": 1, "start_slot": 0, "end_slot": 28},
            {"id": 3, "staff_id": S_MARCUS, "day": 2, "start_slot": 0, "end_slot": 28},
        ],
        "rooms": [
            _room(R_B104, "B1.04", "Cyber Lab 1", "on-campus", 20),
            _room(R_B105, "B1.05", "Cyber Lab 2", "on-campus", 20),
            _room(R_A201, "A2.01", "Classroom A2.01", "on-campus", 25),
            _room(R_A202, "A2.02", "Classroom A2.02", "on-campus", 30),
            _room(R_A110, "A1.10", "Seminar Room", "on-campus", 12),
            _room(R_W101, "W1.01", "Workshop", "on-campus", 16),
            _room(R_ONL1, "ONL-1", "Online Delivery", "online", 99),
        ],
        # 24 pre-placed bookings. Slots: 2=09:00, 4=10:00, 6=11:00, 8=12:00,
        # 10=13:00, 12=14:00, 14=15:00, 16=16:00.
        "bookings": [
            # --- CYB-A (Cyber Threat Intelligence left unplaced for M3) ---
            _booking(1, CYB_A, U_NETSEC, S_TOM, R_B104, 0, 4, 8),      # Mon 10-12 (clash pair)
            _booking(2, CYB_A, U_SECPROG, S_PRIYA, R_B105, 1, 2, 8),   # Tue 09-12
            _booking(3, CYB_A, U_LINUX, S_MARCUS, R_B104, 2, 12, 16),  # Wed 14-16
            _booking(4, CYB_A, U_INCIDENT, S_TOM, R_B104, 2, 2, 6, part=1),   # Wed 09-11
            _booking(5, CYB_A, U_INCIDENT, S_TOM, R_B104, 3, 2, 6, part=2),   # Thu 09-11
            _booking(6, CYB_A, U_WEBSEC, S_AISHA, R_B105, 0, 10, 14),  # Mon 13-15
            _booking(7, CYB_A, U_WORKCOM, S_ELENA, R_A201, 1, 10, 14), # Tue 13-15
            # --- CYB-B (fully scheduled; carries the M4 traps) ---
            _booking(8, CYB_B, U_NETSEC, S_JAMES, R_B104, 3, 8, 12, lock_time=1),  # Thu 12-14
            _booking(9, CYB_B, U_THREAT, S_TOM, R_B105, 1, 10, 14),    # Tue 13-15
            _booking(10, CYB_B, U_SECPROG, S_DAVID, R_B105, 2, 8, 14), # Wed 12-15 (David: soft)
            _booking(11, CYB_B, U_LINUX, S_TOM, R_ONL1, 0, 6, 10),     # Mon 11-13 (clash + room_type)
            _booking(12, CYB_B, U_INCIDENT, S_PRIYA, R_B104, 4, 2, 6, part=1),   # Fri 09-11
            _booking(13, CYB_B, U_INCIDENT, S_PRIYA, R_B104, 4, 8, 12, part=2),  # Fri 12-14
            _booking(14, CYB_B, U_WEBSEC, S_AISHA, R_B105, 3, 2, 6),   # Thu 09-11
            _booking(15, CYB_B, U_WORKCOM, S_ELENA, R_A202, 2, 2, 6),  # Wed 09-11
            # --- CHC-A (Community Services; capacity + availability traps) ---
            _booking(16, CHC_A, U_FIRSTAID, S_SARAH, R_A110, 1, 2, 10),  # Tue 09-13 (12 seats!)
            _booking(17, CHC_A, U_CASEMGMT, S_MARCUS, R_A201, 3, 4, 8),  # Thu 10-12 (unavailable)
            _booking(18, CHC_A, U_LEGAL, S_ELENA, R_A201, 0, 10, 14),    # Mon 13-15 (M5 cover)
            _booking(19, CHC_A, U_COUNSEL, S_SARAH, R_A202, 0, 4, 10, lock_time=1),  # Mon 10-13
            _booking(20, CHC_A, U_DIGLIT, S_PRIYA, R_ONL1, 2, 2, 6),     # Wed 09-11 (M5 reassign)
            # --- CYB-T (capstone group; most classes left in holding) ---
            _booking(21, CYB_T, U_THREAT, S_JAMES, R_B105, 4, 2, 6),   # Fri 09-11
            _booking(22, CYB_T, U_SECPROG, S_PRIYA, R_B105, 0, 4, 10), # Mon 10-13
            _booking(23, CYB_T, U_LINUX, S_MARCUS, R_B104, 2, 8, 12),  # Wed 12-14
            _booking(24, CYB_T, U_WEBSEC, S_AISHA, R_A202, 1, 4, 8),   # Tue 10-12
        ],
    }

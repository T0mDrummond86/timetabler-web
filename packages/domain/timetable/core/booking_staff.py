"""Staff roles attached to a scheduled booking."""
from __future__ import annotations

import re
from typing import Literal

from sqlalchemy import and_, or_

from .models import Booking

_IMPORT_LECTURER_SCOPE_RE = re.compile(
    r"\s*\(\s*(T1(?:\s*\+\s*T2)?|T2(?:\s*\+\s*T1)?)\s*\)\s*$",
    re.I,
)

TermFilter = Literal["all", "t1", "t2"]


def has_sfs_co_teacher(booking: Booking) -> bool:
    return getattr(booking, "sfs_co_teacher_staff_id", None) is not None


def sfs_co_teacher_booking_filter():
    """SQLAlchemy filter: bookings with an assigned SFS co-teacher."""
    return Booking.sfs_co_teacher_staff_id.isnot(None)


def _effective_sfs_co_teacher_terms(booking: Booking) -> tuple[bool, bool]:
    """Co-teach term flags; if both unset but a co-teacher is assigned, mirror class terms."""
    if not has_sfs_co_teacher(booking):
        return False, False
    t1 = bool(getattr(booking, "sfs_co_teacher_in_term_1", 0))
    t2 = bool(getattr(booking, "sfs_co_teacher_in_term_2", 0))
    if not t1 and not t2:
        return bool(getattr(booking, "in_term_1", 1)), bool(getattr(booking, "in_term_2", 1))
    return t1, t2


def sfs_co_teacher_in_term_1(booking: Booking) -> bool:
    if not has_sfs_co_teacher(booking):
        return False
    return bool(getattr(booking, "sfs_co_teacher_in_term_1", 0))


def sfs_co_teacher_in_term_2(booking: Booking) -> bool:
    if not has_sfs_co_teacher(booking):
        return False
    return bool(getattr(booking, "sfs_co_teacher_in_term_2", 0))


def lane_terms_for_staff_view(booking: Booking, staff_id: int) -> tuple[bool, bool]:
    """Which T1/T2 lane columns to use when drawing this booking on a staff timetable."""
    if booking.staff_id == staff_id:
        return bool(getattr(booking, "in_term_1", 1)), bool(getattr(booking, "in_term_2", 1))
    if getattr(booking, "sfs_co_teacher_staff_id", None) == staff_id:
        t1 = staff_active_in_term(booking, staff_id, "t1")
        t2 = staff_active_in_term(booking, staff_id, "t2")
        return t1, t2
    return False, False


def export_lecturer_label(
    booking: Booking,
    *,
    term: Literal["t1", "t2"] | None = None,
) -> str:
    """Primary and SFS co-teacher names for workbook export cells.

    When ``term`` is ``t1`` or ``t2``, only lecturers active in that term are included
    (for admin export label columns). Otherwise both names are shown, with a short
    co-teach scope suffix when it is not the full semester.
    """
    primary = (booking.staff.name if booking.staff else "") or ""
    if not has_sfs_co_teacher(booking):
        if term == "t1" and not getattr(booking, "in_term_1", 1):
            return ""
        if term == "t2" and not getattr(booking, "in_term_2", 1):
            return ""
        return primary

    co = getattr(booking, "sfs_co_teacher", None)
    co_id = getattr(booking, "sfs_co_teacher_staff_id", None)
    co_name = (co.name if co else "") or (f"staff #{co_id}" if co_id else "")
    in_t1 = bool(getattr(booking, "in_term_1", 1))
    in_t2 = bool(getattr(booking, "in_term_2", 1))
    co_t1, co_t2 = _effective_sfs_co_teacher_terms(booking)

    def _join(names: list[str]) -> str:
        return " + ".join(n for n in names if n)

    if term == "t1":
        names: list[str] = []
        if in_t1 and primary:
            names.append(primary)
        if in_t1 and co_t1 and co_name:
            names.append(co_name)
        return _join(names)

    if term == "t2":
        names = []
        if in_t2 and primary:
            names.append(primary)
        if in_t2 and co_t2 and co_name:
            names.append(co_name)
        return _join(names)

    names = []
    if primary:
        names.append(primary)
    if co_name and co_name not in names:
        names.append(co_name)
    line = _join(names)
    co_t1_eff, co_t2_eff = _effective_sfs_co_teacher_terms(booking)
    if co_t1_eff and co_t2_eff and in_t1 and in_t2:
        return line
    scope_parts: list[str] = []
    if co_t1_eff and not (co_t2_eff and in_t2):
        scope_parts.append("T1")
    if co_t2_eff and not (co_t1_eff and in_t1):
        scope_parts.append("T2")
    if scope_parts and line:
        return f"{line} ({'+'.join(scope_parts)})"
    return line


def parse_import_lecturer_label(
    text: str,
) -> tuple[str | None, str | None, bool | None, bool | None]:
    """Parse admin/overall export lecturer cells written by :func:`export_lecturer_label`.

    Returns ``(primary_name, co_teacher_name, co_in_term_1, co_in_term_2)``.
    Co-teach term flags are ``None`` when no co-teacher is present, or when the
    co-teacher applies to the same terms as the class (inherit from booking).
    """
    s = (text or "").strip()
    if not s:
        return None, None, None, None

    co_t1: bool | None = None
    co_t2: bool | None = None
    scope_match = _IMPORT_LECTURER_SCOPE_RE.search(s)
    if scope_match:
        scope = scope_match.group(1).upper().replace(" ", "")
        s = s[: scope_match.start()].strip()
        if "T1" in scope:
            co_t1 = True
        if "T2" in scope:
            co_t2 = True
        if co_t1 and not co_t2:
            co_t2 = False
        elif co_t2 and not co_t1:
            co_t1 = False

    parts = [p.strip() for p in re.split(r"\s+\+\s+", s) if p.strip()]
    if not parts:
        return None, None, None, None

    primary = parts[0]
    co = parts[1] if len(parts) > 1 else None
    if co is None:
        return primary, None, None, None
    if co_t1 is None and co_t2 is None:
        return primary, co, None, None
    return primary, co, co_t1, co_t2


def apply_parsed_lecturers_to_booking(
    booking: Booking,
    *,
    primary_name: str | None,
    co_teacher_name: str | None,
    co_in_term_1: bool | None,
    co_in_term_2: bool | None,
    resolve_staff_id,
) -> None:
    """Set ``staff_id`` and optional SFS co-teacher fields on a new booking."""
    booking.staff_id = resolve_staff_id(primary_name) if primary_name else None
    if not co_teacher_name:
        return
    booking.sfs_co_teacher_staff_id = resolve_staff_id(co_teacher_name)
    if co_in_term_1 is not None and co_in_term_2 is not None:
        booking.sfs_co_teacher_in_term_1 = 1 if co_in_term_1 else 0
        booking.sfs_co_teacher_in_term_2 = 1 if co_in_term_2 else 0
    else:
        booking.sfs_co_teacher_in_term_1 = 0
        booking.sfs_co_teacher_in_term_2 = 0


def sfs_co_teacher_term_labels(booking: Booking) -> str:
    """Short label for cards/tooltips, e.g. 'T1', 'T2', 'T1+T2'."""
    if not has_sfs_co_teacher(booking):
        return ""
    t1 = sfs_co_teacher_in_term_1(booking)
    t2 = sfs_co_teacher_in_term_2(booking)
    if t1 and t2:
        return "T1+T2"
    if t1:
        return "T1"
    if t2:
        return "T2"
    return ""


def staff_name_on_booking(booking: Booking, staff_id: int) -> str:
    """Display name for a staff member in this booking's role."""
    if booking.staff_id == staff_id and booking.staff is not None:
        return booking.staff.name
    co = getattr(booking, "sfs_co_teacher", None)
    if getattr(booking, "sfs_co_teacher_staff_id", None) == staff_id and co is not None:
        return co.name
    return f"staff #{staff_id}"


def staff_active_in_term(booking: Booking, staff_id: int, term: Literal["t1", "t2"]) -> bool:
    """Whether ``staff_id`` is teaching or co-teaching this booking in ``term``."""
    in_t1 = bool(getattr(booking, "in_term_1", 1))
    in_t2 = bool(getattr(booking, "in_term_2", 1))
    if term == "t1":
        if not in_t1:
            return False
        if booking.staff_id == staff_id:
            return True
        if booking.sfs_co_teacher_staff_id == staff_id:
            return _effective_sfs_co_teacher_terms(booking)[0]
        return False
    if not in_t2:
        return False
    if booking.staff_id == staff_id:
        return True
    if booking.sfs_co_teacher_staff_id == staff_id:
        return _effective_sfs_co_teacher_terms(booking)[1]
    return False


def staff_active_in_term_filter(
    booking: Booking, staff_id: int, term_filter: TermFilter
) -> bool:
    if term_filter == "t1":
        return staff_active_in_term(booking, staff_id, "t1")
    if term_filter == "t2":
        return staff_active_in_term(booking, staff_id, "t2")
    return staff_active_in_term(booking, staff_id, "t1") or staff_active_in_term(
        booking, staff_id, "t2"
    )


def staff_terms_overlap_on_bookings(a: Booking, b: Booking, staff_id: int) -> bool:
    """True if ``staff_id`` is active on both bookings in at least one shared term."""
    return staff_active_in_term(a, staff_id, "t1") and staff_active_in_term(
        b, staff_id, "t1"
    ) or staff_active_in_term(a, staff_id, "t2") and staff_active_in_term(b, staff_id, "t2")


def staff_ids_with_term_overlap(a: Booking, b: Booking) -> set[int]:
    """Staff who occupy both bookings in at least one shared term (for clash checks)."""
    ids = set(timetable_staff_ids(a)) | set(timetable_staff_ids(b))
    return {sid for sid in ids if staff_terms_overlap_on_bookings(a, b, sid)}


def timetable_staff_ids(booking: Booking) -> list[int]:
    """Staff who occupy this block on timetables in at least one term."""
    ids: list[int] = []
    if booking.staff_id is not None:
        ids.append(booking.staff_id)
    co = getattr(booking, "sfs_co_teacher_staff_id", None)
    if co is not None and co not in ids:
        if sfs_co_teacher_in_term_1(booking) or sfs_co_teacher_in_term_2(booking):
            ids.append(co)
    return ids


def staff_booking_hours_by_term(booking: Booking, staff_id: int) -> tuple[float, float]:
    """Scheduled slot hours attributed to ``staff_id`` in T1 and T2 (may sum both)."""
    from .staff_hours import booking_duration_hours

    hrs = booking_duration_hours(booking)
    t1 = hrs if staff_active_in_term(booking, staff_id, "t1") else 0.0
    t2 = hrs if staff_active_in_term(booking, staff_id, "t2") else 0.0
    return t1, t2


def staff_booking_filter_sql(staff_id: int, term_filter: TermFilter):
    """SQLAlchemy filter for staff-view bookings including term-scoped co-teaching."""
    primary = Booking.staff_id == staff_id
    co = Booking.sfs_co_teacher_staff_id == staff_id
    if term_filter == "t1":
        return or_(
            and_(primary, Booking.in_term_1 == 1),
            and_(co, Booking.in_term_1 == 1, Booking.sfs_co_teacher_in_term_1 == 1),
        )
    if term_filter == "t2":
        return or_(
            and_(primary, Booking.in_term_2 == 1),
            and_(co, Booking.in_term_2 == 1, Booking.sfs_co_teacher_in_term_2 == 1),
        )
    return or_(
        primary,
        and_(
            co,
            or_(
                and_(Booking.in_term_1 == 1, Booking.sfs_co_teacher_in_term_1 == 1),
                and_(Booking.in_term_2 == 1, Booking.sfs_co_teacher_in_term_2 == 1),
            ),
        ),
    )

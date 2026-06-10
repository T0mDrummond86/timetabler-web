"""Resolve LAP lecturer row values from timetable bookings."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from .booking_staff import has_sfs_co_teacher
from .models import Booking, Unit

_NMTAFE_EMAIL_DOMAIN = "nmtafe.wa.edu.au"
_LAP_PHONE_PLACEHOLDER = "N/A"
_LAP_CONTACT_TIMES = "regular business hours"


def _lecturer_names_for_unit(session: Session, unit_id: int, week_id: int) -> list[str]:
    bookings = (
        session.query(Booking)
        .filter(Booking.unit_id == unit_id, Booking.week_id == week_id)
        .order_by(Booking.course_id, Booking.staff_id)
        .all()
    )
    names: list[str] = []
    seen: set[str] = set()
    for booking in bookings:
        if booking.staff:
            label = (booking.staff.name or "").strip()
            if label and label not in seen:
                seen.add(label)
                names.append(label)
        if has_sfs_co_teacher(booking):
            co = getattr(booking, "sfs_co_teacher", None)
            co_id = getattr(booking, "sfs_co_teacher_staff_id", None)
            co_name = (co.name if co else "") or (f"staff #{co_id}" if co_id else "")
            co_name = co_name.strip()
            if co_name and co_name not in seen:
                seen.add(co_name)
                names.append(co_name)
    return names


def _normalise_email_local_part(part: str) -> str:
    return re.sub(r"[^a-z0-9]", "", part.casefold())


def nmtafe_email_from_name(name: str) -> str:
    """``[first name].[last name]@nmtafe.wa.edu.au`` from a staff display name."""
    cleaned = re.sub(r"\s*\(.*\)\s*$", "", (name or "").strip())
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return ""
    if len(tokens) == 1:
        local = _normalise_email_local_part(tokens[0])
    else:
        local = (
            f"{_normalise_email_local_part(tokens[0])}."
            f"{_normalise_email_local_part(tokens[-1])}"
        )
    return f"{local}@{_NMTAFE_EMAIL_DOMAIN}" if local else ""


def nmtafe_emails_from_display_name(display_name: str) -> str:
    """One or more lecturer emails joined for compound ``A + B`` name cells."""
    parts = [p.strip() for p in (display_name or "").split(" + ") if p.strip()]
    emails = [nmtafe_email_from_name(part) for part in parts]
    emails = [email for email in emails if email]
    return "; ".join(emails)


def lap_lecturers_for_unit(
    session: Session,
    unit: Unit,
    *,
    week_id: int,
) -> list[dict[str, str]]:
    """One LAP lecturer-table row per assigned staff member."""
    return [
        {
            "name": name,
            "phone": _LAP_PHONE_PLACEHOLDER,
            "email": nmtafe_email_from_name(name),
            "contact_times": _LAP_CONTACT_TIMES,
        }
        for name in _lecturer_names_for_unit(session, unit.id, week_id)
    ]


def lap_lecturer_fields_for_unit(
    session: Session,
    unit: Unit,
    *,
    week_id: int,
) -> dict[str, str]:
    """Build LAP lecturer-row values from current timetable assignments."""
    lecturers = lap_lecturers_for_unit(session, unit, week_id=week_id)
    name = " + ".join(l["name"] for l in lecturers)
    return {
        "name": name,
        "phone": _LAP_PHONE_PLACEHOLDER,
        "email": nmtafe_emails_from_display_name(name),
        "contact_times": _LAP_CONTACT_TIMES,
    }

"""PDF export for lecturer cover assignments."""
from __future__ import annotations

import io

from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session, joinedload

from ..core.models import Booking, Staff
from .timetable_print_layout import PrintCardDraw, TimetablePrintPage
from .timetable_print_pdf import PAGE_SIZE, _draw_page


def _cover_card_lines(booking: Booking) -> tuple[str, ...]:
    unit = (booking.unit.name if booking.unit else "") or "Class"
    group = (booking.course.code if booking.course else "") or ""
    room = (booking.room.code if booking.room else "") or "—"
    regular = (booking.staff.name if booking.staff else "") or "—"
    cover = (booking.cover_staff.name if booking.cover_staff else "") or "—"
    lines = [unit]
    if group:
        lines.append(group)
    lines.extend([room, f"Regular: {regular}", f"Cover: {cover}"])
    return tuple(lines)


def cover_bookings_for_export(
    session: Session,
    *,
    week_id: int,
    staff_id: int | None = None,
) -> list[Booking]:
    q = (
        session.query(Booking)
        .options(
            joinedload(Booking.unit),
            joinedload(Booking.course),
            joinedload(Booking.staff),
            joinedload(Booking.cover_staff),
            joinedload(Booking.room),
        )
        .filter(Booking.week_id == week_id, Booking.cover_staff_id.isnot(None))
    )
    if staff_id is not None:
        q = q.filter(Booking.staff_id == staff_id)
    return q.order_by(Booking.day, Booking.start_slot).all()


def build_cover_print_page(
    bookings: list[Booking],
    *,
    title: str,
) -> TimetablePrintPage:
    cards: list[PrintCardDraw] = []
    for b in bookings:
        cards.append(
            PrintCardDraw(
                day=b.day,
                start_slot=b.start_slot,
                end_slot=b.end_slot,
                sub_lane=0,
                sub_lane_count=1,
                lane="full",
                lines=_cover_card_lines(b),
                fill_hex="#dbeafe",
                booking_id=b.id,
                violation=None,
            )
        )
    return TimetablePrintPage(
        headline=title,
        kind="staff",
        cards=tuple(cards),
        unavailable_by_day=None,
    )


def render_cover_timetable_pdf(
    session: Session,
    *,
    week_id: int,
    staff_id: int | None = None,
    week_label: str | None = None,
) -> bytes:
    bookings = cover_bookings_for_export(session, week_id=week_id, staff_id=staff_id)
    if staff_id is not None:
        staff = session.get(Staff, staff_id)
        name = staff.name if staff else f"Staff #{staff_id}"
        title = f"Lecturer cover — {name}"
    else:
        title = "Lecturer cover timetable"
    if week_label:
        title = f"{title} ({week_label})"
    page = build_cover_print_page(bookings, title=title)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE_SIZE)
    _draw_page(c, page)
    c.save()
    return buf.getvalue()

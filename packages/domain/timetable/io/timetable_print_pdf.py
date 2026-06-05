"""Render timetable print pages to PDF (A4 landscape, desktop parity)."""
from __future__ import annotations

import io
import xml.sax.saxutils as sax
from typing import Sequence

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfgen import canvas

from ..constants import DAYS, NUM_DAYS, NUM_SLOTS, slot_to_time
from .timetable_print_layout import (
    PrintKind,
    TimetablePrintPage,
    build_print_page,
    collect_print_colour_map,
)

PAGE_SIZE = landscape(A4)
_INDEX_BOOKMARK = "timetable_index"
_KIND_INDEX_TITLE = {
    "course": "Course timetables",
    "staff": "Staff timetables",
    "room": "Room timetables",
}
_MARGIN_PT = 14
_TITLE_PT = 16
_HDR_PT = 9
_TIME_PT = 7
_CARD_PAD_PT = 3
_CARD_PAD_LEFT_PT = 5
_TABLE_LINE_PT = 0.75


def _hex(color: str):
    return HexColor(color)


def _card_rect(
    grid_left: float,
    grid_top: float,
    day_block_w: float,
    slot_h: float,
    *,
    day: int,
    start_slot: int,
    end_slot: int,
    sub_lane: int,
    sub_lane_count: int,
    lane: str,
) -> tuple[float, float, float, float]:
    """Return (x, y, width, height) with reportlab bottom-left origin."""
    count = max(1, sub_lane_count)
    w = day_block_w / count
    x = grid_left + day * day_block_w + sub_lane * w
    if lane == "left":
        w /= 2
    elif lane == "right":
        x += w / 2
        w /= 2
    y = grid_top - end_slot * slot_h
    ch = max(1.0, (end_slot - start_slot) * slot_h)
    return x, y, w, ch


def _paragraph(text: str, width: float, max_height: float, *, bold: bool) -> tuple[Paragraph | None, float]:
    """Build a wrapped paragraph that fits in max_height."""
    face = "Helvetica-Bold" if bold else "Helvetica"
    for size_x10 in range(100, 50, -1):
        pt = size_x10 / 10.0
        style = ParagraphStyle(
            name="card",
            fontName=face,
            fontSize=pt,
            leading=pt * 1.15,
            alignment=TA_LEFT,
            textColor=black,
            spaceBefore=0,
            spaceAfter=0,
        )
        para = Paragraph(sax.escape(text), style)
        _, ph = para.wrap(width, max_height)
        if ph <= max_height + 0.5:
            return para, ph
    style = ParagraphStyle(
        name="cardMin",
        fontName=face,
        fontSize=5,
        leading=5.75,
        alignment=TA_LEFT,
        textColor=black,
    )
    para = Paragraph(sax.escape(text[:120]), style)
    _, ph = para.wrap(width, max_height)
    return para, min(ph, max_height)


def _draw_card_text(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    lines: tuple[str, ...],
) -> None:
    """Draw placecard lines top-down inside the card rect (desktop print parity)."""
    if not lines or w < 4 or h < 4:
        return
    pad = _CARD_PAD_PT
    pad_l = _CARD_PAD_LEFT_PT
    inner_x = x + pad_l
    inner_w = max(4.0, w - pad_l - pad)
    inner_bottom = y + pad
    inner_top = y + h - pad
    inner_h = inner_top - inner_bottom
    if inner_h < 4 or inner_w < 4:
        return

    title_budget = inner_h * (0.45 if len(lines) > 2 else (0.55 if len(lines) > 1 else 1.0))
    cursor_top = inner_top

    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        if idx == 0:
            budget = title_budget
        else:
            budget = cursor_top - inner_bottom
        if budget < 3:
            break
        para, ph = _paragraph(line, inner_w, budget, bold=(idx == 0))
        if para is None or ph <= 0:
            continue
        para.drawOn(c, inner_x, cursor_top - ph)
        cursor_top -= ph + 1.0


def _draw_page(c: canvas.Canvas, page: TimetablePrintPage) -> None:
    w, h = PAGE_SIZE
    c.setPageSize(PAGE_SIZE)
    c.setFillColor(white)
    c.rect(0, 0, w, h, fill=1, stroke=0)

    pr_left = _MARGIN_PT
    pr_bottom = _MARGIN_PT
    content_top = h - _MARGIN_PT
    pr_width = w - 2 * _MARGIN_PT
    title_h = 24
    hdr_h = 16

    # Match desktop: title, then header row, then slot grid.
    header_bottom = content_top - title_h - hdr_h
    grid_top = header_bottom
    grid_bottom = pr_bottom
    grid_h = grid_top - grid_bottom
    time_w = max(36, pr_width * 0.05)
    grid_left = pr_left + time_w
    grid_width = pr_width - time_w
    day_block_w = grid_width / NUM_DAYS
    slot_h = grid_h / NUM_SLOTS
    header_top = header_bottom + hdr_h

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", _TITLE_PT)
    c.drawCentredString(pr_left + pr_width / 2, content_top - title_h / 2 - 4, page.headline)

    c.setStrokeColor(black)
    c.setLineWidth(_TABLE_LINE_PT)

    # Horizontal grid lines (slot rows).
    for s in range(NUM_SLOTS + 1):
        y = grid_top - s * slot_h
        c.line(pr_left, y, pr_left + pr_width, y)
    # Table outer top (below title).
    c.line(pr_left, header_top, pr_left + pr_width, header_top)

    xs = [pr_left, pr_left + time_w]
    for d in range(NUM_DAYS + 1):
        xs.append(grid_left + d * day_block_w)
    for x in xs:
        c.line(x, pr_bottom, x, header_top)

    header_fill = _hex("#e9ecef")
    c.setFillColor(header_fill)
    c.rect(pr_left, header_bottom, time_w, hdr_h, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", _HDR_PT)
    c.drawCentredString(pr_left + time_w / 2, header_bottom + hdr_h / 2 - 3, "Time")
    for d, name in enumerate(DAYS):
        hx = grid_left + d * day_block_w
        c.setFillColor(header_fill)
        c.rect(hx, header_bottom, day_block_w, hdr_h, fill=1, stroke=0)
        c.setFillColor(black)
        c.drawCentredString(hx + day_block_w / 2, header_bottom + hdr_h / 2 - 3, name)

    c.setFont("Helvetica", _TIME_PT)
    c.setFillColor(_hex("#374151"))
    for s in range(NUM_SLOTS):
        ty = grid_top - (s + 0.5) * slot_h - _TIME_PT * 0.35
        label = slot_to_time(s).strftime("%H:%M")
        c.drawRightString(pr_left + time_w - 4, ty, label)

    if page.unavailable_by_day:
        c.setFillColor(_hex("#E5E7EB"))
        c.setStrokeColor(_hex("#E5E7EB"))
        for day, slots in page.unavailable_by_day.items():
            for s in slots:
                if 0 <= s < NUM_SLOTS:
                    cx, cy, cw, ch = _card_rect(
                        grid_left,
                        grid_top,
                        day_block_w,
                        slot_h,
                        day=day,
                        start_slot=s,
                        end_slot=s + 1,
                        sub_lane=0,
                        sub_lane_count=1,
                        lane="full",
                    )
                    c.rect(cx, cy, cw, ch, fill=1, stroke=0)

    c.setFillColor(black)
    c.setStrokeColor(black)
    for card in page.cards:
        x, y, cw, ch = _card_rect(
            grid_left,
            grid_top,
            day_block_w,
            slot_h,
            day=card.day,
            start_slot=card.start_slot,
            end_slot=card.end_slot,
            sub_lane=card.sub_lane,
            sub_lane_count=card.sub_lane_count,
            lane=card.lane,
        )
        if cw < 2 or ch < 2:
            continue
        c.setFillColor(_hex(card.fill_hex))
        c.rect(x, y, cw, ch, fill=1, stroke=0)
        if card.violation == "hard":
            c.setStrokeColor(_hex("#DC2626"))
            c.setLineWidth(2.0)
        elif card.violation == "soft":
            c.setStrokeColor(_hex("#D97706"))
            c.setLineWidth(1.5)
        else:
            c.setStrokeColor(black)
            c.setLineWidth(0.75)
        c.rect(x, y, cw, ch, fill=0, stroke=1)
        if card.lane in ("left", "right"):
            full_x, full_y, full_w, full_h = _card_rect(
                grid_left,
                grid_top,
                day_block_w,
                slot_h,
                day=card.day,
                start_slot=card.start_slot,
                end_slot=card.end_slot,
                sub_lane=card.sub_lane,
                sub_lane_count=card.sub_lane_count,
                lane="full",
            )
            mid_x = full_x + full_w / 2
            c.line(mid_x, full_y, mid_x, full_y + full_h)
        _draw_card_text(c, x, y, cw, ch, card.lines)


def _bookmark_key(kind: PrintKind, entity_id: int) -> str:
    return f"tt_{kind}_{entity_id}"


def _draw_index_page(
    c: canvas.Canvas,
    *,
    kind: PrintKind,
    week_label: str | None,
    entities: Sequence[tuple[int, str]],
) -> None:
    """First page: clickable list of timetables (Excel-style tab navigation)."""
    w, h = PAGE_SIZE
    c.setPageSize(PAGE_SIZE)
    c.setFillColor(white)
    c.rect(0, 0, w, h, fill=1, stroke=0)

    c.bookmarkPage(_INDEX_BOOKMARK)
    c.addOutlineEntry("Index", _INDEX_BOOKMARK, level=0)

    margin = _MARGIN_PT
    y = h - margin - 28
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, y, _KIND_INDEX_TITLE.get(kind, "Timetables"))
    y -= 22

    if week_label:
        c.setFont("Helvetica", 11)
        c.setFillColor(_hex("#374151"))
        c.drawString(margin, y, f"Week: {week_label}")
        y -= 18

    c.setFont("Helvetica", 10)
    c.setFillColor(_hex("#555555"))
    c.drawString(
        margin,
        y,
        "Click a name below to jump to that timetable (or use the PDF bookmarks panel).",
    )
    y -= 22

    line_h = 16
    link_w = w - 2 * margin
    c.setFont("Helvetica", 11)
    for eid, label in entities:
        if y < margin + line_h:
            c.showPage()
            c.setPageSize(PAGE_SIZE)
            y = h - margin - 20
        key = _bookmark_key(kind, eid)
        link_y1 = y - 2
        link_y2 = y + line_h - 2
        c.linkRect(
            "",
            key,
            Rect=(margin, link_y1, margin + link_w, link_y2),
            relative=0,
            addtopage=1,
        )
        c.setFillColor(_hex("#1d4ed8"))
        c.drawString(margin, y, label)
        y -= line_h

    c.showPage()


def render_timetable_print_pdf(
    session,
    *,
    week_id: int,
    kind: PrintKind,
    entities: Sequence[tuple[int, str]],
    term_filter: str = "all",
    colour_by_class: bool = True,
    week_label: str | None = None,
    include_index: bool = True,
) -> bytes:
    """One landscape A4 page per entity; returns PDF bytes."""
    from ..core.validation import validate_bookings

    violations = validate_bookings(session, week_id)
    colour_map = collect_print_colour_map(
        session,
        week_id=week_id,
        kind=kind,
        entity_ids=[eid for eid, _ in entities],
        term_filter=term_filter,
        colour_by_class=colour_by_class,
        violations_cache=violations,
    )
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE_SIZE)

    if include_index and len(entities) > 1:
        _draw_index_page(c, kind=kind, week_label=week_label, entities=entities)

    for i, (eid, label) in enumerate(entities):
        if i > 0:
            c.showPage()
        key = _bookmark_key(kind, eid)
        c.bookmarkPage(key)
        c.addOutlineEntry(label, key, level=0)
        page = build_print_page(
            session,
            week_id=week_id,
            kind=kind,
            entity_id=eid,
            label=label,
            term_filter=term_filter,
            colour_by_class=colour_by_class,
            violations_cache=violations,
            colour_map=colour_map,
        )
        _draw_page(c, page)
    c.save()
    return buf.getvalue()

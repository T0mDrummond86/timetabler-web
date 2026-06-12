"""Placecard geometry for interactive timetable grids (term bands + clash lanes)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from .models import Booking
from .staff_hours import room_is_online
from .validation import bookings_need_separate_lanes

TermLayout = Literal["full", "t1_only", "t2_only", "term_pair", "merged_online"]


@dataclass(frozen=True)
class PlacecardRect:
    left_pct: float
    width_pct: float


@dataclass(frozen=True)
class _PaintUnit:
    bookings: tuple[Booking, ...]
    term_layout: TermLayout


def _term_flag(booking: Booking, name: str, *, default: int = 1) -> bool:
    raw = getattr(booking, name, None)
    if raw is None:
        return bool(default)
    if isinstance(raw, bool):
        return raw
    try:
        return bool(int(raw))
    except (TypeError, ValueError):
        return bool(default)


def terms_of(b: Booking) -> tuple[bool, bool]:
    return _term_flag(b, "in_term_1"), _term_flag(b, "in_term_2")


def _intervals_overlap(a: Booking, b: Booking) -> bool:
    return a.start_slot < b.end_slot and b.start_slot < a.end_slot


def _term_band(b: Booking) -> PlacecardRect:
    t1, t2 = terms_of(b)
    if t1 and t2:
        return PlacecardRect(0.0, 100.0)
    if t1:
        return PlacecardRect(0.0, 50.0)
    if t2:
        return PlacecardRect(50.0, 50.0)
    return PlacecardRect(0.0, 100.0)


def _should_merge_online_slot(group: list[Booking]) -> bool:
    if len(group) < 2:
        return False
    if not all(room_is_online(b.room) for b in group):
        return False
    return len({b.staff_id for b in group}) == 1


def _split_pairs(
    bookings: list[Booking],
) -> tuple[list[Booking], list[tuple[Booking, Booking]]]:
    by_slot: dict[tuple[int, int, int], list[Booking]] = defaultdict(list)
    for b in bookings:
        by_slot[(b.day, b.start_slot, b.end_slot)].append(b)
    solo: list[Booking] = []
    pairs: list[tuple[Booking, Booking]] = []
    for group in by_slot.values():
        if len(group) == 2:
            t1_only = [b for b in group if terms_of(b) == (True, False)]
            t2_only = [b for b in group if terms_of(b) == (False, True)]
            if len(t1_only) == 1 and len(t2_only) == 1:
                pairs.append((t1_only[0], t2_only[0]))
                continue
        solo.extend(group)
    return solo, pairs


def units_for_slot_group(group: list[Booking]) -> list[_PaintUnit]:
    if _should_merge_online_slot(group):
        return [_PaintUnit(tuple(group), "merged_online")]
    solos, pairs = _split_pairs(group)
    units: list[_PaintUnit] = []
    for t1_b, t2_b in pairs:
        units.append(_PaintUnit((t1_b, t2_b), "term_pair"))
    for b in solos:
        t1, t2 = terms_of(b)
        if t1 and t2:
            units.append(_PaintUnit((b,), "full"))
        elif t1:
            units.append(_PaintUnit((b,), "t1_only"))
        elif t2:
            units.append(_PaintUnit((b,), "t2_only"))
        else:
            units.append(_PaintUnit((b,), "full"))
    return units


def _assign_lanes(bookings: list[Booking]) -> tuple[dict[int, int], int]:
    sorted_b = sorted(bookings, key=lambda b: (b.start_slot, b.end_slot))
    lane_index: dict[int, int] = {}
    lanes: list[list[Booking]] = []
    for b in sorted_b:
        placed = False
        for i, occupants in enumerate(lanes):
            if any(bookings_need_separate_lanes(b, x) for x in occupants):
                continue
            occupants.append(b)
            lane_index[b.id] = i
            placed = True
            break
        if not placed:
            lanes.append([b])
            lane_index[b.id] = len(lanes) - 1
    return lane_index, max(1, len(lanes))


def _lane_depth_for_booking(booking: Booking, cluster: list[Booking]) -> int:
    depth = 1
    for t in range(booking.start_slot, booking.end_slot):
        active = [b for b in cluster if b.start_slot <= t < b.end_slot]
        _, n_at = _assign_lanes(active)
        depth = max(depth, n_at)
    return depth


def _apply_unit_layout(
    layouts: dict[int, PlacecardRect],
    *,
    unit: _PaintUnit,
    unit_left: float,
    unit_width: float,
) -> None:
    if unit.term_layout == "merged_online":
        for b in unit.bookings:
            layouts[b.id] = PlacecardRect(unit_left, unit_width)
        return
    if unit.term_layout == "term_pair":
        t1_b, t2_b = unit.bookings
        half = unit_width / 2.0
        layouts[t1_b.id] = PlacecardRect(unit_left, half)
        layouts[t2_b.id] = PlacecardRect(unit_left + half, half)
        return
    b = unit.bookings[0]
    if unit.term_layout == "full":
        layouts[b.id] = PlacecardRect(unit_left, unit_width)
    elif unit.term_layout == "t1_only":
        layouts[b.id] = PlacecardRect(unit_left, unit_width / 2.0)
    elif unit.term_layout == "t2_only":
        layouts[b.id] = PlacecardRect(unit_left + unit_width / 2.0, unit_width / 2.0)


def _overlap_components(bookings: list[Booking]) -> list[list[Booking]]:
    if not bookings:
        return []
    ordered = sorted(bookings, key=lambda b: (b.start_slot, b.end_slot, b.id))
    parent = {b.id: b.id for b in ordered}

    def find(booking_id: int) -> int:
        root = booking_id
        while parent[root] != root:
            parent[root] = parent[parent[root]]
            root = parent[root]
        return root

    def union(a_id: int, b_id: int) -> None:
        ra, rb = find(a_id), find(b_id)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if _intervals_overlap(a, b):
                union(a.id, b.id)

    grouped: dict[int, list[Booking]] = defaultdict(list)
    for b in ordered:
        grouped[find(b.id)].append(b)
    return list(grouped.values())


def _layout_overlap_component(
    component: list[Booking],
    layouts: dict[int, PlacecardRect],
) -> None:
    pending = [b for b in component if b.id not in layouts]
    if not pending:
        return

    by_exact: dict[tuple[int, int, int], list[Booking]] = defaultdict(list)
    for b in pending:
        by_exact[(b.day, b.start_slot, b.end_slot)].append(b)

    still: list[Booking] = []
    for group in by_exact.values():
        if len(group) >= 2:
            units = units_for_slot_group(group)
            if len(units) == 1 and units[0].term_layout == "term_pair":
                _apply_unit_layout(
                    layouts,
                    unit=units[0],
                    unit_left=0.0,
                    unit_width=100.0,
                )
                continue
            if not (
                len(units) == 1
                and units[0].term_layout in ("t1_only", "t2_only", "full")
            ):
                unit_count = len(units)
                for unit_idx, unit in enumerate(units):
                    unit_left = (100.0 / unit_count) * unit_idx
                    unit_width = 100.0 / unit_count
                    _apply_unit_layout(
                        layouts,
                        unit=unit,
                        unit_left=unit_left,
                        unit_width=unit_width,
                    )
                continue
        still.extend(group)

    still = [b for b in {b.id: b for b in still}.values() if b.id not in layouts]
    if not still:
        return

    lane_index, _ = _assign_lanes(still)
    for b in still:
        band = _term_band(b)
        depth = _lane_depth_for_booking(b, still)
        lane = lane_index.get(b.id, 0)
        inner_width = band.width_pct / depth
        inner_left = band.left_pct + lane * inner_width
        layouts[b.id] = PlacecardRect(inner_left, inner_width)


def layout_column_bookings(bookings: list[Booking]) -> dict[int, PlacecardRect]:
    """Map booking id → horizontal position within one timetable column."""
    if not bookings:
        return {}

    layouts: dict[int, PlacecardRect] = {}
    for component in _overlap_components(bookings):
        _layout_overlap_component(component, layouts)

    for b in bookings:
        layouts.setdefault(b.id, _term_band(b))

    return layouts

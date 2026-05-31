"""Canonical room delivery types (on-campus, off-campus, online)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Room

ROOM_TYPE_ON_CAMPUS = "on-campus"
ROOM_TYPE_OFF_CAMPUS = "off-campus"
ROOM_TYPE_ONLINE = "online"

ROOM_TYPES = (ROOM_TYPE_ON_CAMPUS, ROOM_TYPE_OFF_CAMPUS, ROOM_TYPE_ONLINE)

ROOM_TYPE_LABELS: dict[str, str] = {
    ROOM_TYPE_ON_CAMPUS: "On-campus",
    ROOM_TYPE_OFF_CAMPUS: "Off-campus",
    ROOM_TYPE_ONLINE: "Online",
}

ROOM_TYPE_CHOICES: tuple[tuple[str, str], ...] = tuple(
    (value, ROOM_TYPE_LABELS[value]) for value in ROOM_TYPES
)

_LEGACY_TO_CANONICAL: dict[str, str] = {
    "general": ROOM_TYPE_ON_CAMPUS,
    "virtual": ROOM_TYPE_ONLINE,
    "on campus": ROOM_TYPE_ON_CAMPUS,
    "off campus": ROOM_TYPE_OFF_CAMPUS,
    "online": ROOM_TYPE_ONLINE,
}


def normalize_room_type(value: str | None) -> str | None:
    """Map stored values (including legacy general/virtual) to a canonical type."""
    if value is None:
        return None
    key = value.strip().lower()
    if not key:
        return None
    if key in ROOM_TYPE_LABELS:
        return key
    return _LEGACY_TO_CANONICAL.get(key)


def room_type_label(value: str | None) -> str:
    canonical = normalize_room_type(value)
    if canonical is None:
        return ROOM_TYPE_LABELS[ROOM_TYPE_ON_CAMPUS]
    return ROOM_TYPE_LABELS.get(canonical, canonical)


def room_type_is_online(value: str | None) -> bool:
    return normalize_room_type(value) == ROOM_TYPE_ONLINE


def room_type_is_physical(value: str | None) -> bool:
    canonical = normalize_room_type(value)
    return canonical in (ROOM_TYPE_ON_CAMPUS, ROOM_TYPE_OFF_CAMPUS)


def room_types_match(required: str | None, actual: str | None) -> bool:
    if not required:
        return True
    return normalize_room_type(required) == normalize_room_type(actual)


def room_is_physical(room: Room | None) -> bool:
    """True for on-campus and off-campus rooms (shown in physical room grids)."""
    if room is None:
        return False
    return room_type_is_physical(room_delivery_type(room))


def room_has_explicit_delivery_type(room: Room) -> bool:
    """True when room_type was set to a canonical on/off/online value (not legacy)."""
    raw = (getattr(room, "room_type", None) or "").strip().lower()
    return raw in ROOM_TYPE_LABELS


def room_delivery_type(room: Room | None) -> str:
    """Resolved delivery type for scheduling and hours."""
    if room is None:
        return ROOM_TYPE_ON_CAMPUS
    if room_has_explicit_delivery_type(room):
        return normalize_room_type(room.room_type) or ROOM_TYPE_ON_CAMPUS
    if room_is_online_by_code_or_name(room):
        return ROOM_TYPE_ONLINE
    return infer_room_type_from_room(room)


def room_counts_as_physical_space(room: Room | None) -> bool:
    """True when double-booking this room should block other physical uses."""
    if room is None:
        return False
    return room_type_is_physical(room_delivery_type(room))


def room_is_online_by_code_or_name(room: Room) -> bool:
    """Heuristic for rooms with no explicit type (import/bootstrap)."""
    for raw in (room.code, room.name or ""):
        t = (raw or "").strip().lower()
        if not t:
            continue
        if t in ("online", "collaborate"):
            return True
        if "online" in t or "collaborate" in t:
            return True
    return False


def infer_room_type_from_room(room: Room) -> str:
    """Default type when unset: online hints → online, else on-campus."""
    if room_is_online_by_code_or_name(room):
        return ROOM_TYPE_ONLINE
    return ROOM_TYPE_ON_CAMPUS

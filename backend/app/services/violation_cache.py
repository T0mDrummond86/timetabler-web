"""Week-level cache for booking validation results (Phase A performance)."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Literal

ClashDetectMode = Literal["auto", "off", "once"]

from sqlalchemy.orm import Session

from timetable.core.models import Booking, Semester, Week
from timetable.core.clash_check_settings import (
    filter_violations_by_clash_settings,
    load_clash_check_settings,
)
from timetable.core.tenancy_models import TimetableSession
from timetable.core.validation import Severity, Violation, validate_bookings

from ..config import settings

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "violations:week:"
_MEMORY: dict[int, list[dict]] = {}
_redis_client: Redis | None = None
_redis_unavailable = False


def _cache_key(week_id: int) -> str:
    return f"{_CACHE_PREFIX}{week_id}"


def _get_redis() -> Redis | None:
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis_client = client
    except Exception as exc:
        logger.info("Violation cache using in-process store (Redis unavailable: %s)", exc)
        _redis_unavailable = True
        return None
    return _redis_client


def _violation_to_dict(v: Violation) -> dict:
    return {
        "severity": v.severity.value,
        "code": v.code,
        "message": v.message,
        "booking_ids": list(v.booking_ids),
    }


def _violation_from_dict(data: dict) -> Violation:
    return Violation(
        severity=Severity(data["severity"]),
        code=data["code"],
        message=data["message"],
        booking_ids=tuple(data.get("booking_ids") or ()),
    )


def _serialize(violations: list[Violation]) -> str:
    return json.dumps([_violation_to_dict(v) for v in violations], separators=(",", ":"))


def _deserialize(raw: str) -> list[Violation]:
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("invalid violation cache payload")
    return [_violation_from_dict(item) for item in payload]


def _read_cache(week_id: int) -> list[Violation] | None:
    client = _get_redis()
    if client is not None:
        try:
            raw = client.get(_cache_key(week_id))
            if raw is not None:
                return _deserialize(raw)
        except Exception as exc:
            logger.warning("Violation cache read failed for week %s: %s", week_id, exc)
    if week_id in _MEMORY:
        return [_violation_from_dict(item) for item in _MEMORY[week_id]]
    return None


def _write_cache(week_id: int, violations: list[Violation]) -> None:
    payload = [_violation_to_dict(v) for v in violations]
    client = _get_redis()
    if client is not None:
        try:
            client.setex(
                _cache_key(week_id),
                settings.violations_cache_ttl_seconds,
                _serialize(violations),
            )
        except Exception as exc:
            logger.warning("Violation cache write failed for week %s: %s", week_id, exc)
    _MEMORY[week_id] = payload


def invalidate_week_violations(week_id: int) -> None:
    """Drop cached validation for one repeating week."""
    client = _get_redis()
    if client is not None:
        try:
            client.delete(_cache_key(week_id))
        except Exception as exc:
            logger.warning("Violation cache delete failed for week %s: %s", week_id, exc)
    _MEMORY.pop(week_id, None)


def week_ids_for_session(db: Session, timetable_session_id: int) -> list[int]:
    return [
        wid
        for (wid,) in (
            db.query(Week.id)
            .join(Semester, Week.semester_id == Semester.id)
            .filter(Semester.timetable_session_id == timetable_session_id)
            .all()
        )
    ]


def invalidate_session_violations(db: Session, timetable_session_id: int) -> None:
    """Drop cached validation for every week in a timetable session."""
    for week_id in week_ids_for_session(db, timetable_session_id):
        invalidate_week_violations(week_id)


def get_week_violations(db: Session, week_id: int) -> list[Violation]:
    """Return validation for all bookings in a week, using cache when warm."""
    cached = _read_cache(week_id)
    if cached is not None:
        return cached
    violations = validate_bookings(db, week_id)
    _write_cache(week_id, violations)
    return violations


def resolve_week_violations(
    db: Session,
    week_id: int,
    clash_detect: ClashDetectMode = "auto",
    *,
    timetable_session_id: int | None = None,
) -> list[Violation]:
    """Resolve violations for a grid load.

    ``off`` skips validation (fast editing). ``once`` forces a fresh pass and
    warms the cache. ``auto`` uses the cache when warm.
    """
    if clash_detect == "off":
        return []
    if clash_detect == "once":
        invalidate_week_violations(week_id)
    violations = get_week_violations(db, week_id)
    if timetable_session_id is not None:
        row = db.get(TimetableSession, timetable_session_id)
        if row is not None:
            settings = load_clash_check_settings(row)
            violations = filter_violations_by_clash_settings(violations, settings)
    return violations


def filter_violations_for_bookings(
    violations: list[Violation],
    bookings: list[Booking],
) -> list[Violation]:
    """Keep violations detectable from a filtered booking subset (grid views)."""
    visible_ids = {b.id for b in bookings}
    if not visible_ids:
        return []
    return [
        v
        for v in violations
        if v.booking_ids and all(bid in visible_ids for bid in v.booking_ids)
    ]


def clear_violation_cache_for_tests() -> None:
    """Reset process-local and Redis violation cache entries (tests only)."""
    _MEMORY.clear()
    client = _get_redis()
    if client is not None:
        try:
            for key in client.scan_iter(match=f"{_CACHE_PREFIX}*"):
                client.delete(key)
        except Exception as exc:
            logger.warning("Violation cache test cleanup failed: %s", exc)

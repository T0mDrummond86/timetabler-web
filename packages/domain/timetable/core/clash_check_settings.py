"""Per-session enable/disable for individual clash checks."""
from __future__ import annotations

import json

from .clash_check_registry import ClashCheckDefinition, all_clash_check_codes, clash_check_catalog
from .tenancy_models import TimetableSession
from .validation import Violation


def default_clash_check_enabled() -> dict[str, bool]:
    catalog = clash_check_catalog()
    return {code: info.default_enabled for code, info in catalog.items()}


def parse_clash_check_settings_json(raw: str | None) -> dict[str, bool]:
    """Merge stored JSON with catalog defaults (unknown keys ignored)."""
    enabled = default_clash_check_enabled()
    if not raw:
        return enabled
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return enabled
    if not isinstance(data, dict):
        return enabled
    for code in all_clash_check_codes():
        if code in data:
            enabled[code] = bool(data[code])
    return enabled


def clash_check_settings_to_json(settings: dict[str, bool]) -> str:
    catalog = clash_check_catalog()
    payload = {code: bool(settings.get(code, info.default_enabled)) for code, info in catalog.items()}
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def enabled_clash_check_codes(settings: dict[str, bool]) -> frozenset[str]:
    return frozenset(code for code, on in settings.items() if on)


def filter_violations_by_clash_settings(
    violations: list[Violation],
    settings: dict[str, bool],
) -> list[Violation]:
    allowed = enabled_clash_check_codes(settings)
    return [v for v in violations if v.code in allowed]


def clash_settings_rows(settings: dict[str, bool]) -> list[dict]:
    """API/UI rows grouped-ready metadata plus current ``enabled`` flag."""
    catalog = clash_check_catalog()
    rows: list[dict] = []
    for code in catalog:
        info: ClashCheckDefinition = catalog[code]
        rows.append(
            {
                "code": code,
                "label": info.label,
                "description": info.description,
                "category": info.category,
                "severity": info.severity,
                "enabled": bool(settings.get(code, info.default_enabled)),
            }
        )
    return rows


def load_clash_check_settings(session_row: TimetableSession) -> dict[str, bool]:
    return parse_clash_check_settings_json(getattr(session_row, "clash_check_settings_json", None))


def save_clash_check_settings(session_row: TimetableSession, settings: dict[str, bool]) -> None:
    session_row.clash_check_settings_json = clash_check_settings_to_json(settings)

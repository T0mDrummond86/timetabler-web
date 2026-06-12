"""Clash check settings parsing and filtering."""
from __future__ import annotations

import json

from timetable.core.clash_check_registry import clash_check_catalog
from timetable.core.clash_check_settings import (
    clash_check_settings_to_json,
    filter_violations_by_clash_settings,
    parse_clash_check_settings_json,
)
from timetable.core.validation import Severity, Violation


def test_defaults_all_enabled():
    settings = parse_clash_check_settings_json(None)
    assert len(settings) == len(clash_check_catalog())
    assert all(settings.values())


def test_parse_stored_json():
    raw = json.dumps({"staff_double_booking": False, "room_capacity": False})
    settings = parse_clash_check_settings_json(raw)
    assert settings["staff_double_booking"] is False
    assert settings["room_capacity"] is False
    assert settings["course_clash"] is True


def test_filter_violations_respects_settings():
    violations = [
        Violation(Severity.HARD, "staff_double_booking", "x", (1, 2)),
        Violation(Severity.HARD, "room_capacity", "y", (3,)),
    ]
    settings = parse_clash_check_settings_json(json.dumps({"staff_double_booking": False}))
    filtered = filter_violations_by_clash_settings(violations, settings)
    assert [v.code for v in filtered] == ["room_capacity"]


def test_round_trip_json():
    settings = parse_clash_check_settings_json(None)
    settings["monday_start_before_930"] = False
    raw = clash_check_settings_to_json(settings)
    again = parse_clash_check_settings_json(raw)
    assert again["monday_start_before_930"] is False
    assert again["staff_double_booking"] is True

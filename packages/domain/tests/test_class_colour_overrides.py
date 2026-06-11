"""Manual per-class placecard colours."""
from timetable.core.class_colour import booking_class_colour_key
from timetable.core.class_colour_overrides import (
    build_screen_colour_map,
    custom_colours_from_units,
    merge_custom_class_colours,
    normalize_screen_fill_colour,
)
from timetable.core.models import Booking, Course, Unit
from timetable.core.screen_colours import assign_screen_colours


def test_normalize_screen_fill_colour_accepts_hash_hex():
    assert normalize_screen_fill_colour("aabbcc") == "#AABBCC"
    assert normalize_screen_fill_colour("#AABBCC") == "#AABBCC"
    assert normalize_screen_fill_colour("") is None
    assert normalize_screen_fill_colour(None) is None


def test_custom_colours_from_units_maps_by_class_name():
    units = [Unit(name="Lab Alpha", screen_fill_colour="#FF1122")]
    colours = custom_colours_from_units(units)
    assert colours["lab alpha"] == ("#FF1122", colours["lab alpha"][1])


def test_merge_custom_class_colours_overrides_auto_assignment():
    auto = assign_screen_colours({"lab alpha", "lab beta"})
    units = [Unit(name="Lab Alpha", screen_fill_colour="#123456")]
    merged = merge_custom_class_colours(auto, units)
    assert merged["lab alpha"][0] == "#123456"
    assert merged["lab beta"] == auto["lab beta"]


def test_build_screen_colour_map_ignores_custom_when_by_course():
    b = Booking(course=Course(code="G1"), unit=Unit(name="Lab Alpha", screen_fill_colour="#123456"))
    colours = build_screen_colour_map([b], colour_by_class=False, units=[b.unit])
    assert colours["G1"][0] != "#123456"


def test_build_screen_colour_map_applies_custom_when_by_class():
    b = Booking(course=Course(code="G1"), unit=Unit(name="Lab Alpha", screen_fill_colour="#123456"))
    colours = build_screen_colour_map([b], colour_by_class=True, units=[b.unit])
    assert colours[booking_class_colour_key(b)][0] == "#123456"

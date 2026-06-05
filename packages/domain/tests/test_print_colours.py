"""Print colour allocator — distinct class fills for PDF."""
import colorsys

from timetable.core.models import Booking, Course, Staff, Unit
from timetable.core.print_colours import (
    _hash_hue,
    _hue_distance,
    assign_print_colours,
    build_print_fill_by_booking_id,
    contrast_ratio_with_print_text,
    print_booking_tint_key,
)


def test_distinct_colours_for_many_classes():
    keys = {f"class-{i}" for i in range(12)}
    colours = assign_print_colours(keys)
    assert len(colours) == 12
    assert len(set(colours.values())) == 12


def test_same_class_name_same_colour():
    u1 = Unit(name="Network Admin Skills 101")
    u2 = Unit(name="Network Admin Skills 101")
    b1 = Booking(id=1, unit=u1, unit_id=10)
    b2 = Booking(id=2, unit=u2, unit_id=11)
    fills = build_print_fill_by_booking_id(
        [b1, b2], colour_by_class=True, hard_ids=set(), soft_ids=set(), for_print=True
    )
    assert fills[1] == fills[2]


def test_different_classes_different_colours():
    names = [
        "Intro Python",
        "Network Security",
        "Workplace Communications",
        "Cyber Security Awareness",
        "System Security",
        "Catchup",
    ]
    bookings = [
        Booking(id=i + 1, unit=Unit(name=n), unit_id=100 + i) for i, n in enumerate(names)
    ]
    fills = build_print_fill_by_booking_id(
        bookings, colour_by_class=True, hard_ids=set(), soft_ids=set(), for_print=True
    )
    assert len(set(fills.values())) == len(names)


def test_incident_response_and_intro_to_networks_differ():
    """Regression: unrelated classes must not share the same fill."""
    names = ["Incident Response", "Intro to networks"]
    bookings = [
        Booking(id=i + 1, unit=Unit(name=n), unit_id=100 + i) for i, n in enumerate(names)
    ]
    fills = build_print_fill_by_booking_id(
        bookings, colour_by_class=True, hard_ids=set(), soft_ids=set(), for_print=True
    )
    assert fills[1] != fills[2]


def test_global_colour_map_stable_per_class():
    """Same class keeps the same colour when passed a pre-built job map."""
    names = ["Incident Response", "Intro to networks", "Workplace Communications"]
    bookings = [
        Booking(id=i + 1, unit=Unit(name=n), unit_id=100 + i) for i, n in enumerate(names)
    ]
    colour_map = assign_print_colours(
        {print_booking_tint_key(b, by_class=True) for b in bookings}
    )
    page_a = build_print_fill_by_booking_id(
        bookings[:2],
        colour_by_class=True,
        hard_ids=set(),
        soft_ids=set(),
        for_print=True,
        colour_map=colour_map,
    )
    page_b = build_print_fill_by_booking_id(
        [bookings[0]],
        colour_by_class=True,
        hard_ids=set(),
        soft_ids=set(),
        for_print=True,
        colour_map=colour_map,
    )
    assert page_a[1] == page_b[1]


def test_assign_print_colours_separates_similar_hash_hues():
    keys = {
        "class alpha",
        "class beta",
        "class gamma",
        "class delta",
        "class epsilon",
        "class zeta",
    }
    colours = assign_print_colours(keys)
    hues = []
    for hex_colour in colours.values():
        r = int(hex_colour[1:3], 16) / 255
        g = int(hex_colour[3:5], 16) / 255
        b = int(hex_colour[5:7], 16) / 255
        hues.append(colorsys.rgb_to_hls(r, g, b)[0])
    for i, h1 in enumerate(hues):
        for h2 in hues[i + 1 :]:
            assert _hue_distance(h1, h2) >= 18 / 360.0


def test_for_print_keeps_class_colour_on_violations():
    b = Booking(id=1, unit=Unit(name="Class A"), unit_id=1)
    fills = build_print_fill_by_booking_id(
        [b], colour_by_class=True, hard_ids={1}, soft_ids=set(), for_print=True
    )
    assert fills[1] != "#FFDCDE"


def test_non_print_mode_still_uses_violation_fill():
    b = Booking(id=1, unit=Unit(name="Class A"), unit_id=1)
    fills = build_print_fill_by_booking_id(
        [b], colour_by_class=True, hard_ids={1}, soft_ids=set(), for_print=False
    )
    assert fills[1] == "#FFDCDE"


def test_unit_id_fallback_when_name_missing():
    b = Booking(id=1, unit=Unit(name=""), unit_id=42)
    assert print_booking_tint_key(b, by_class=True) == "unit:42"


def test_course_mode_uses_course_code():
    b = Booking(id=1, course=Course(code="CIV1"), course_id=5)
    assert print_booking_tint_key(b, by_class=False) == "course:civ1"


def test_all_assigned_colours_readable_with_card_text():
    keys = {f"unit class {i}" for i in range(30)}
    for hex_colour in assign_print_colours(keys).values():
        assert contrast_ratio_with_print_text(hex_colour) >= 3.0, hex_colour


def test_hash_hue_stable_for_key():
    assert _hash_hue("incident response") == _hash_hue("incident response")
    assert _hash_hue("incident response") != _hash_hue("intro to networks")

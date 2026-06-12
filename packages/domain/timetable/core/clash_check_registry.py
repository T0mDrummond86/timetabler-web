"""Catalog of clash / constraint checks surfaced in the timetable UI."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClashCheckDefinition:
    code: str
    label: str
    description: str
    category: str
    severity: str  # "hard" | "soft"
    default_enabled: bool = True


def clash_check_catalog() -> dict[str, ClashCheckDefinition]:
    """Stable violation ``code`` → metadata (matches :mod:`validation`)."""
    items: tuple[ClashCheckDefinition, ...] = (
        ClashCheckDefinition(
            "room_double_booking",
            "Room double-booking",
            "Same physical room booked twice at overlapping times.",
            "clashes",
            "hard",
        ),
        ClashCheckDefinition(
            "staff_double_booking",
            "Staff double-booking",
            "Same lecturer assigned to overlapping classes (except permitted online cohort overlap).",
            "clashes",
            "hard",
        ),
        ClashCheckDefinition(
            "course_clash",
            "Course class overlap",
            "Two classes for the same course cohort overlap in time.",
            "clashes",
            "hard",
        ),
        ClashCheckDefinition(
            "lecturer_not_allowed",
            "Lecturer not on allowed list",
            "Assigned lecturer is not on the class allowed-lecturers list.",
            "staff",
            "soft",
        ),
        ClashCheckDefinition(
            "staff_unavailable",
            "Staff unavailable",
            "Class scheduled outside the lecturer's recorded availability windows.",
            "staff",
            "hard",
        ),
        ClashCheckDefinition(
            "staff_hour_cap",
            "Staff weekly hour cap",
            "Lecturer exceeds their max hours per week (per term).",
            "staff",
            "soft",
        ),
        ClashCheckDefinition(
            "qualification_time_window",
            "Qualification time window",
            "Class scheduled outside the qualification's allowed day/time windows.",
            "qualification",
            "hard",
        ),
        ClashCheckDefinition(
            "room_not_allowed",
            "Room not on allowed list",
            "Room is not on the class allowed-rooms list.",
            "rooms",
            "hard",
        ),
        ClashCheckDefinition(
            "room_capacity",
            "Room too small",
            "Room capacity is below the class required capacity.",
            "rooms",
            "hard",
        ),
        ClashCheckDefinition(
            "room_type",
            "Wrong room type",
            "Room type does not match the class requirement.",
            "rooms",
            "hard",
        ),
        ClashCheckDefinition(
            "friday_finish_after_6pm",
            "Friday finish after 18:00",
            "A class finishes after 18:00 on Friday.",
            "scheduling",
            "hard",
        ),
        ClashCheckDefinition(
            "monday_start_before_930",
            "Monday start before 09:30",
            "A class starts before 09:30 on Monday.",
            "scheduling",
            "soft",
        ),
        ClashCheckDefinition(
            "staff_break_every_6h",
            "6-hour teaching without break",
            "Lecturer has more than 6 hours of teaching in a row without a 30-minute break.",
            "scheduling",
            "hard",
        ),
        ClashCheckDefinition(
            "staff_idle_gap_over_2h",
            "Staff idle gap over 2 hours",
            "More than 2 hours between classes for the same lecturer on one day.",
            "scheduling",
            "soft",
        ),
        ClashCheckDefinition(
            "staff_daily_hours_below_5",
            "Staff under 5 hours (teaching day)",
            "Lecturer teaches fewer than 5 hours on a day they have classes.",
            "scheduling",
            "soft",
        ),
        ClashCheckDefinition(
            "staff_daily_hours_above_9",
            "Staff over 9 hours (teaching day)",
            "Lecturer teaches more than 9 hours on one day.",
            "scheduling",
            "soft",
        ),
        ClashCheckDefinition(
            "student_daily_hours_below_5",
            "Student cohort under 5 hours",
            "Course cohort has fewer than 5 hours of classes on a day.",
            "scheduling",
            "soft",
        ),
        ClashCheckDefinition(
            "student_daily_hours_above_8",
            "Student cohort over 8 hours",
            "Course cohort has more than 8 hours of classes on a day.",
            "scheduling",
            "soft",
        ),
        ClashCheckDefinition(
            "student_idle_gap_over_2h",
            "Student break over 2 hours",
            "More than 2 hours between classes for the same course cohort on one day.",
            "scheduling",
            "soft",
        ),
    )
    return {d.code: d for d in items}


def clash_check_category_labels() -> dict[str, str]:
    return {
        "clashes": "Double-booking & clashes",
        "staff": "Staff rules",
        "rooms": "Room rules",
        "qualification": "Qualification",
        "scheduling": "Scheduling rules",
    }


def all_clash_check_codes() -> frozenset[str]:
    return frozenset(clash_check_catalog())

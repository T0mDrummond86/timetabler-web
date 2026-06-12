"""API must expose placecard layout geometry for term-band rendering."""

from app.schemas import BookingCardOut, TimetableGridOut


def _minimal_card(**overrides) -> dict:
    base = {
        "id": 1,
        "course_id": 10,
        "day": 2,
        "column": 2,
        "start_slot": 20,
        "end_slot": 24,
        "lane": 0,
        "lane_depth": 1,
        "layout_left_pct": 0.0,
        "layout_width_pct": 50.0,
        "unit_name": "Demo unit",
        "course_code": "DEMO",
        "staff_name": "Staff",
        "room_code": "R1",
        "room_id": 1,
        "notes": None,
        "external_id": None,
        "colour_key": "demo",
        "fill_colour": "#cccccc",
        "border_colour": "#999999",
        "is_hard": False,
        "is_soft": False,
        "violations": [],
    }
    base.update(overrides)
    return base


def test_booking_card_out_preserves_layout_geometry():
    card = BookingCardOut.model_validate(_minimal_card())
    assert card.layout_left_pct == 0.0
    assert card.layout_width_pct == 50.0


def test_timetable_grid_out_serializes_term_band_layout():
    grid = TimetableGridOut.model_validate(
        {
            "timetable_session_id": 1,
            "view": "course",
            "entity_id": 10,
            "entity_label": "Demo",
            "course_id": 10,
            "course_code": "DEMO",
            "week_id": 1,
            "week_label": "Repeating",
            "column_kind": "day",
            "columns": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "num_slots": 28,
            "slot_minutes": 30,
            "first_slot_time": "08:30",
            "bookings": [
                _minimal_card(id=1, layout_left_pct=0.0, layout_width_pct=50.0),
                _minimal_card(
                    id=2,
                    layout_left_pct=50.0,
                    layout_width_pct=50.0,
                    in_term_1=False,
                    in_term_2=True,
                ),
            ],
            "violations": [],
        }
    )
    dumped = grid.model_dump()
    t1 = next(b for b in dumped["bookings"] if b["id"] == 1)
    t2 = next(b for b in dumped["bookings"] if b["id"] == 2)
    assert t1["layout_left_pct"] == 0.0
    assert t1["layout_width_pct"] == 50.0
    assert t2["layout_left_pct"] == 50.0
    assert t2["layout_width_pct"] == 50.0

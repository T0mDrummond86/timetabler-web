"""Removing a change from the admin-export markup must apply to that change
only — a later edit to the same class is a new change and must be logged and
marked up normally."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parents[1]
DOMAIN = BACKEND.parent / "packages" / "domain"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(DOMAIN))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["JWT_SECRET"] = "test-secret"

from timetable.core.change_log_data import (  # noqa: E402
    admin_export_highlights_by_booking_id,
    gather_timetabling_change_log_display_rows,
)
from timetable.core.models import (  # noqa: E402
    Base,
    Booking,
    ChangeLogEntry,
    Course,
    Room,
    Semester,
    Staff,
    Unit,
    Week,
)
from timetable.core.tenancy_models import Organization, TimetableSession  # noqa: E402

from app.services.change_log import set_change_log_highlight_removed  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


class World:
    """One class with a room change, then a second room change."""

    def __init__(self, db):
        self.db = db
        org = Organization(name="Acme", slug="acme")
        db.add(org)
        db.flush()
        ts = TimetableSession(organization_id=org.id, name="S1")
        db.add(ts)
        db.flush()
        self.session_id = ts.id

        sem = Semester(timetable_session_id=ts.id, name="S1")
        db.add(sem)
        db.flush()
        week = Week(semester_id=sem.id, week_number=0)
        db.add(week)
        db.flush()

        course = Course(timetable_session_id=ts.id, code="CYB-A")
        unit = Unit(timetable_session_id=ts.id, name="Networking")
        staff = Staff(timetable_session_id=ts.id, name="Tom")
        self.rooms = [Room(timetable_session_id=ts.id, code=c) for c in ("A101", "A102", "A103")]
        db.add_all([course, unit, staff, *self.rooms])
        db.flush()

        self.booking = Booking(
            week_id=week.id,
            course_id=course.id,
            unit_id=unit.id,
            staff_id=staff.id,
            room_id=self.rooms[0].id,
            day=0,
            start_slot=2,
            end_slot=6,
            external_id="4401238",
        )
        db.add(self.booking)
        db.commit()

    def _state(self, room_id: int) -> dict:
        b = self.booking
        return {
            "course_id": b.course_id,
            "unit_id": b.unit_id,
            "staff_id": b.staff_id,
            "room_id": room_id,
            "day": b.day,
            "start_slot": b.start_slot,
            "end_slot": b.end_slot,
            "external_id": b.external_id,
        }

    def log_room_move(self, from_room: int, to_room: int) -> int:
        """Record a change entry the way the app does, and move the booking."""
        import json

        entry = ChangeLogEntry(
            timetable_session_id=self.session_id,
            action="change",
            description="room move",
            details=json.dumps(
                {
                    "bookings": {
                        str(self.booking.id): {
                            "before": self._state(from_room),
                            "after": self._state(to_room),
                        }
                    }
                }
            ),
        )
        self.db.add(entry)
        self.booking.room_id = to_room
        self.db.commit()
        return entry.id

    def resolved_row(self):
        rows = gather_timetabling_change_log_display_rows(
            self.db, timetable_session_id=self.session_id, resolved=True
        )
        return next((r for r in rows if r.booking_id == self.booking.id), None)

    def highlighted(self) -> bool:
        hl = admin_export_highlights_by_booking_id(
            self.db, timetable_session_id=self.session_id
        )
        return str(self.booking.id) in hl


def test_removal_hides_the_change_it_was_applied_to(db):
    w = World(db)
    entry1 = w.log_room_move(w.rooms[0].id, w.rooms[1].id)

    assert w.resolved_row().removed is False
    assert w.highlighted() is True

    set_change_log_highlight_removed(
        db,
        timetable_session_id=w.session_id,
        entry_id=entry1,
        booking_id=w.booking.id,
        removed=True,
    )
    row = w.resolved_row()
    assert row is not None, "a removed change must stay visible in the log"
    assert row.removed is True
    assert w.highlighted() is False


def test_a_later_change_to_the_same_class_is_logged_and_marked_up(db):
    """The reported bug: the second change inherited the first one's removal."""
    w = World(db)
    entry1 = w.log_room_move(w.rooms[0].id, w.rooms[1].id)
    set_change_log_highlight_removed(
        db,
        timetable_session_id=w.session_id,
        entry_id=entry1,
        booking_id=w.booking.id,
        removed=True,
    )
    assert w.highlighted() is False

    # Change the same class again.
    w.log_room_move(w.rooms[1].id, w.rooms[2].id)

    row = w.resolved_row()
    assert row is not None
    assert row.removed is False, "a new change must not inherit an earlier removal"
    assert row.row["room_change"] == "A101 → A103"
    assert w.highlighted() is True, "the new change must reach the admin export"


def test_the_new_change_can_be_removed_in_its_own_right(db):
    w = World(db)
    entry1 = w.log_room_move(w.rooms[0].id, w.rooms[1].id)
    set_change_log_highlight_removed(
        db,
        timetable_session_id=w.session_id,
        entry_id=entry1,
        booking_id=w.booking.id,
        removed=True,
    )
    entry2 = w.log_room_move(w.rooms[1].id, w.rooms[2].id)

    set_change_log_highlight_removed(
        db,
        timetable_session_id=w.session_id,
        entry_id=entry2,
        booking_id=w.booking.id,
        removed=True,
    )
    assert w.resolved_row().removed is True
    assert w.highlighted() is False


def test_restore_brings_the_change_back(db):
    w = World(db)
    entry1 = w.log_room_move(w.rooms[0].id, w.rooms[1].id)
    for removed in (True, False):
        set_change_log_highlight_removed(
            db,
            timetable_session_id=w.session_id,
            entry_id=entry1,
            booking_id=w.booking.id,
            removed=removed,
        )
    assert w.resolved_row().removed is False
    assert w.highlighted() is True

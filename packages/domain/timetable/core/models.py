"""SQLAlchemy ORM models for the timetabling app.

Glossary
========
The domain has three words that all sound related but mean different things:

  Course        — a *cohort/group* of students (e.g. "BFF7 CIII IT GrpA").
                  Has a code; each Course has many Bookings during the week.
  Unit (model)  — a *class* in user-facing terms (e.g. "Cyber Foundations").
                  This is what the UI calls a "Class" and what gets booked.
                  Each row defines a class's length, allowed lecturers, etc.
  Qualification — a *parent qualification* (e.g. "BFF7 CIII IT") a Unit
                  belongs to. May restrict scheduling time windows.

The free-text `Unit.component_codes` column lists the underlying
units-of-study identifiers that make up the class (e.g. VU23217, ICTICT443).
This avoids the visually-jarring `Unit.units` it replaced.

Slot model
==========
Each booking occupies a contiguous range of half-hour slots on a given
(week, day). Long classes are stored as a single row, not per-slot rows.
"""
from __future__ import annotations

import datetime as _dt

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ..constants import NUM_DAYS, NUM_SLOTS


class Base(DeclarativeBase):
    pass


class Semester(Base):
    # Web: each semester belongs to one timetable session (desktop: one SQLite file).
    """Single-row placeholder.

    Currently every session has exactly one Semester (Week 0 inside it) and
    all bookings reference it. The table is kept as a hook for future
    per-week or per-semester scheduling (skip-weeks, exam weeks, public
    holidays), but right now its `num_weeks` and `repeating` columns are not
    consulted anywhere — the in-app term tags (`Booking.in_term_1` /
    `in_term_2`) cover all current variation.

    To finish per-week support later: store distinct bookings per Week,
    expose a week-picker in the toolbar, and update validators/solver to
    iterate weeks instead of treating Week 0 as the whole semester.
    """
    __tablename__ = "semester"
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_session_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_session.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String)
    num_weeks: Mapped[int] = mapped_column(Integer, default=18)
    repeating: Mapped[int] = mapped_column(Integer, default=1)

    weeks: Mapped[list["Week"]] = relationship(back_populates="semester", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("timetable_session_id", "name", name="semester_session_name_uk"),)


class Week(Base):
    """Single-row placeholder. See `Semester` docstring for context."""
    __tablename__ = "week"
    id: Mapped[int] = mapped_column(primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semester.id", ondelete="CASCADE"))
    week_number: Mapped[int] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String, nullable=True)

    semester: Mapped[Semester] = relationship(back_populates="weeks")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="week", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("semester_id", "week_number"),)


class Room(Base):
    __tablename__ = "room"
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_session_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_session.id", ondelete="CASCADE"),
        index=True,
    )
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    room_type: Mapped[str | None] = mapped_column(String, nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("timetable_session_id", "code", name="room_session_code_uk"),)


class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_session_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_session.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String)
    cost_centre: Mapped[str | None] = mapped_column(String(80), nullable=True)
    max_hours_per_week: Mapped[float | None] = mapped_column(nullable=True)
    non_teaching_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Full-time equivalent (input); lecturing load = fte × 21 hours per FTE.
    fte: Mapped[float | None] = mapped_column(nullable=True)
    # Spreadsheet-style hour inputs (columns F, I, J, K); added to column L total.
    ot_hours: Mapped[float | None] = mapped_column(nullable=True)
    development_project_hours: Mapped[float | None] = mapped_column(nullable=True)
    development_project_description: Mapped[str | None] = mapped_column(String, nullable=True)
    tae_hours: Mapped[float | None] = mapped_column(nullable=True)
    supervision_hours: Mapped[float | None] = mapped_column(nullable=True)
    # Headcount per online session when a booking has no online_student_count.
    default_online_students_per_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When set, all bookings for this lecturer keep times and lecturers (solver/clear).
    timetable_locked: Mapped[int] = mapped_column(Integer, default=0)
    # Order in the timetable sidebar SELECT list (lower = higher).
    sidebar_order: Mapped[int] = mapped_column(Integer, default=0)

    availability: Mapped[list["StaffAvailability"]] = relationship(
        back_populates="staff", cascade="all, delete-orphan"
    )
    competencies: Mapped[list["StaffCompetency"]] = relationship(
        back_populates="staff", cascade="all, delete-orphan"
    )
    preferences: Mapped[list["StaffPreference"]] = relationship(
        back_populates="staff", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("timetable_session_id", "name", name="staff_session_name_uk"),)


class StaffAvailability(Base):
    """A window when a staff member is available to teach. Multiple rows allowed per staff."""
    __tablename__ = "staff_availability"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"))
    day: Mapped[int] = mapped_column(Integer)
    start_slot: Mapped[int] = mapped_column(Integer)
    end_slot: Mapped[int] = mapped_column(Integer)  # exclusive

    staff: Mapped[Staff] = relationship(back_populates="availability")

    __table_args__ = (
        CheckConstraint(f"day >= 0 AND day < {NUM_DAYS}", name="avail_day_ck"),
        CheckConstraint(
            f"start_slot >= 0 AND end_slot > start_slot AND end_slot <= {NUM_SLOTS}",
            name="avail_slot_ck",
        ),
    )


class Unit(Base):
    """A "class" — the thing a lecturer delivers to a course. Was historically
    called a "unit" in the source spreadsheet; the user-facing label is now
    "Class" but the table name is preserved for migration simplicity.
    """
    __tablename__ = "unit"
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_session_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_session.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String)
    length_slots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Comma-separated list of underlying study-unit codes that compose this
    # class (e.g. "VU23217, ICTICT443"). Free text; the UI labels it "Units".
    component_codes: Mapped[str | None] = mapped_column("units", String, nullable=True)
    required_room_type: Mapped[str | None] = mapped_column(String, nullable=True)
    required_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Double session: two bookings per (course, class); see double_session_* columns.
    double_session: Mapped[int] = mapped_column(Integer, default=0)
    double_session_same_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    double_session_first_slots: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("timetable_session_id", "name", name="unit_session_name_uk"),)


class Qualification(Base):
    """A parent qualification (e.g. 'BFF7 CIII IT'). One class may belong to
    multiple qualifications.

    `num_groups` is the number of cohorts (Courses) the qualification has —
    one Course per group, named '{qual} GrpA', '{qual} GrpB', etc. Saving
    the qualification ensures that many group-courses exist.
    """
    __tablename__ = "qualification"
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_session_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_session.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String)
    num_groups: Mapped[int] = mapped_column(Integer, default=1)
    # ``day`` (08:30–19:00) or ``night`` (17:30–21:30); drives qualification_time_window rows.
    schedule_period: Mapped[str] = mapped_column(String, default="day")
    # ``regular`` = repeating weekly semester delivery; ``block`` = 1–3 week intensive block.
    delivery_mode: Mapped[str] = mapped_column(String, default="regular")
    block_week_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_start_semester_week: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("timetable_session_id", "name", name="qualification_session_name_uk"),
    )


class QualificationTimeWindow(Base):
    """Allowed time window for any class that belongs to this qualification.

    If a qualification has no rows in this table, classes inheriting from it
    have no time constraint. Otherwise, a booking must fit entirely within
    one of the windows.
    """
    __tablename__ = "qualification_time_window"
    id: Mapped[int] = mapped_column(primary_key=True)
    qualification_id: Mapped[int] = mapped_column(
        ForeignKey("qualification.id", ondelete="CASCADE")
    )
    day: Mapped[int] = mapped_column(Integer)
    start_slot: Mapped[int] = mapped_column(Integer)
    end_slot: Mapped[int] = mapped_column(Integer)  # exclusive

    __table_args__ = (
        CheckConstraint(f"day >= 0 AND day < {NUM_DAYS}", name="qual_window_day_ck"),
        CheckConstraint(
            f"start_slot >= 0 AND end_slot > start_slot AND end_slot <= {NUM_SLOTS}",
            name="qual_window_slot_ck",
        ),
    )


class UnitQualification(Base):
    __tablename__ = "unit_qualification"
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"), primary_key=True)
    qualification_id: Mapped[int] = mapped_column(ForeignKey("qualification.id", ondelete="CASCADE"), primary_key=True)


class UnitAllowedRoom(Base):
    """A room that's allowed for a given class. Empty list = no restriction."""
    __tablename__ = "unit_allowed_room"
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"), primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id", ondelete="CASCADE"), primary_key=True)


class StaffCompetency(Base):
    __tablename__ = "staff_competency"
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"), primary_key=True)

    staff: Mapped[Staff] = relationship(back_populates="competencies")
    unit: Mapped[Unit] = relationship()


class StaffQualificationOnlineStudents(Base):
    """Per-lecturer online cohort size for a qualification (total students)."""
    __tablename__ = "staff_qualification_online_students"
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True)
    qualification_id: Mapped[int] = mapped_column(
        ForeignKey("qualification.id", ondelete="CASCADE"), primary_key=True
    )
    student_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class StaffUnitOnlineStudents(Base):
    """Per-lecturer online cohort size for a class with no qualification link."""
    __tablename__ = "staff_unit_online_students"
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"), primary_key=True)
    student_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class StaffPreference(Base):
    """Imported lecturer class preferences from preference templates."""
    __tablename__ = "staff_preference"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(Integer)  # 1=first, 2=second, 3=third
    slot_number: Mapped[int] = mapped_column(Integer)  # 1..2 within each priority
    qualification_name: Mapped[str | None] = mapped_column(String, nullable=True)
    class_name: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("unit.id", ondelete="SET NULL"), nullable=True)

    staff: Mapped[Staff] = relationship(back_populates="preferences")
    unit: Mapped[Unit | None] = relationship()

    __table_args__ = (
        UniqueConstraint("staff_id", "priority", "slot_number", name="staff_pref_staff_priority_slot_uk"),
        CheckConstraint("priority >= 1 AND priority <= 3", name="staff_pref_priority_ck"),
        CheckConstraint("slot_number >= 1 AND slot_number <= 2", name="staff_pref_slot_ck"),
    )


class Course(Base):
    """A course group (e.g. 'CIV Cybr Stg1 GrpA') — the cohort that attends together.

    Optionally linked to a Qualification (one cohort = one parent qualification).
    """
    __tablename__ = "course"
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_session_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_session.id", ondelete="CASCADE"),
        index=True,
    )
    code: Mapped[str] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    qualification_id: Mapped[int | None] = mapped_column(
        ForeignKey("qualification.id", ondelete="SET NULL"), nullable=True
    )
    # When set, all bookings for this cohort keep times and lecturers (solver/clear).
    timetable_locked: Mapped[int] = mapped_column(Integer, default=0)
    # Order in the timetable sidebar SELECT list (lower = higher).
    sidebar_order: Mapped[int] = mapped_column(Integer, default=0)
    # Block delivery: length and start week per cohort group (null = inherit qualification default).
    block_week_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_start_semester_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Block delivery cohorts are separate from regular semester group courses.
    is_block_cohort: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("timetable_session_id", "code", name="course_session_code_uk"),)


class CourseUnit(Base):
    """Units that a course delivers in the semester."""
    __tablename__ = "course_unit"
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"), primary_key=True)


class Booking(Base):
    """A scheduled class block: course + unit + staff + room on (week, day, slot range)."""
    __tablename__ = "booking"
    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("week.id", ondelete="CASCADE"))
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"))
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("unit.id", ondelete="SET NULL"), nullable=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"), nullable=True)
    sfs_co_teacher_staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), nullable=True
    )
    # SFS co-teaching may apply in one or both terms (subset of in_term_1 / in_term_2).
    sfs_co_teacher_in_term_1: Mapped[int] = mapped_column(Integer, default=0)
    sfs_co_teacher_in_term_2: Mapped[int] = mapped_column(Integer, default=0)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("room.id", ondelete="SET NULL"), nullable=True)
    day: Mapped[int] = mapped_column(Integer)
    start_slot: Mapped[int] = mapped_column(Integer)
    end_slot: Mapped[int] = mapped_column(Integer)  # exclusive
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    # Per-instance identifier shown on the timetable card. Used as a quick
    # human-readable tag for this specific booking; same class can have a
    # different ID in each cohort.
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Each booking is active in one or both terms. Default: both (matches the
    # most common case, and means existing imports keep their semantics).
    in_term_1: Mapped[int] = mapped_column(Integer, default=1)
    in_term_2: Mapped[int] = mapped_column(Integer, default=1)
    # Headcount for online-room load (see staff_hours); null = default 20.
    online_student_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Timetable locks (also inherited from staff/course timetable_locked).
    lock_time: Mapped[int] = mapped_column(Integer, default=0)
    lock_staff: Mapped[int] = mapped_column(Integer, default=0)
    # 1 or 2 when the class uses double sessions; 1 for a normal single booking.
    session_part: Mapped[int] = mapped_column(Integer, default=1)
    # JSON list of active semester week numbers (1–20); null = all applicable weeks.
    session_weeks: Mapped[str | None] = mapped_column(String, nullable=True)
    # Block delivery: which week within the block (1–3); null = regular repeating booking.
    block_week_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    week: Mapped[Week] = relationship(back_populates="bookings")
    course: Mapped[Course] = relationship()
    unit: Mapped[Unit | None] = relationship()
    staff: Mapped[Staff | None] = relationship(foreign_keys=[staff_id])
    sfs_co_teacher: Mapped[Staff | None] = relationship(foreign_keys=[sfs_co_teacher_staff_id])
    room: Mapped[Room | None] = relationship()

    __table_args__ = (
        CheckConstraint(f"day >= 0 AND day < {NUM_DAYS}", name="booking_day_ck"),
        CheckConstraint(
            f"start_slot >= 0 AND end_slot > start_slot AND end_slot <= {NUM_SLOTS}",
            name="booking_slot_ck",
        ),
    )


class ChangeLogEntry(Base):
    """An audit row for a user-initiated change in this session."""
    __tablename__ = "change_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_session_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_session.id", ondelete="CASCADE"),
        index=True,
    )
    ts: Mapped[_dt.datetime] = mapped_column(
        DateTime,
        default=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
    )
    action: Mapped[str] = mapped_column(String)        # e.g. 'edit', 'move', 'undo', 'import'
    description: Mapped[str] = mapped_column(String)   # short human-readable summary
    details: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON blob for context

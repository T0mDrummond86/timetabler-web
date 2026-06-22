"""Schema migrations driven by an explicit version registry.

Each migration is a (version, callable) pair. The DB stamps its current
schema version into a `schema_version` table; on startup we apply any
migration whose version is greater than the stored one.

Migrations are forward-only — there are no downgrades.

Adding a new migration
======================
1. Append a new `_mNN(...)` function below the existing ones.
2. Bump the next sequential version and register it in MIGRATIONS.
3. Test on a fresh DB *and* on a copy of an existing one.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy.engine import Connection, Engine


# (version, description, function(conn))
MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = []


def _migration(version: int, description: str):
    """Decorator that registers a function as a migration."""
    def wrapper(fn: Callable[[Connection], None]):
        MIGRATIONS.append((version, description, fn))
        return fn
    return wrapper


# ---- Helpers ----

def _columns_of(conn: Connection, table: str) -> set[str]:
    try:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    except Exception:
        return set()
    return {r[1] for r in rows}


def _table_exists(conn: Connection, table: str) -> bool:
    rows = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchall()
    return bool(rows)


# ---- Migrations ----

@_migration(1, "Add booking.notes")
def _m1(conn: Connection) -> None:
    if "notes" not in _columns_of(conn, "booking"):
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN notes TEXT")


@_migration(2, "Add booking.in_term_1 / in_term_2")
def _m2(conn: Connection) -> None:
    cols = _columns_of(conn, "booking")
    if "in_term_1" not in cols:
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN in_term_1 INTEGER DEFAULT 1")
    if "in_term_2" not in cols:
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN in_term_2 INTEGER DEFAULT 1")


@_migration(3, "Add unit.external_id / length_slots / units")
def _m3(conn: Connection) -> None:
    cols = _columns_of(conn, "unit")
    if "external_id" not in cols:
        conn.exec_driver_sql("ALTER TABLE unit ADD COLUMN external_id TEXT")
    if "length_slots" not in cols:
        conn.exec_driver_sql("ALTER TABLE unit ADD COLUMN length_slots INTEGER")
    if "units" not in cols:
        conn.exec_driver_sql("ALTER TABLE unit ADD COLUMN units TEXT")


@_migration(4, "Rename unit.code -> unit.name")
def _m4(conn: Connection) -> None:
    cols = _columns_of(conn, "unit")
    if "code" in cols and "name" not in cols:
        conn.exec_driver_sql("ALTER TABLE unit RENAME COLUMN code TO name")
    elif "code" in cols and "name" in cols:
        conn.exec_driver_sql(
            "UPDATE unit SET name = COALESCE(NULLIF(name, ''), code)"
            " WHERE name IS NULL OR name = ''"
        )


@_migration(5, "Rename qualification.code -> qualification.name")
def _m5(conn: Connection) -> None:
    if not _table_exists(conn, "qualification"):
        return
    cols = _columns_of(conn, "qualification")
    if "code" in cols and "name" not in cols:
        conn.exec_driver_sql("ALTER TABLE qualification RENAME COLUMN code TO name")
    elif "code" in cols and "name" in cols:
        conn.exec_driver_sql(
            "UPDATE qualification SET name = COALESCE(NULLIF(name, ''), code)"
            " WHERE name IS NULL OR name = ''"
        )


@_migration(8, "Add Booking.external_id (per-instance class identifier)")
def _m8(conn: Connection) -> None:
    cols = _columns_of(conn, "booking")
    if "external_id" not in cols:
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN external_id TEXT")


@_migration(10, "Add staff.fte and booking.online_student_count")
def _m10(conn: Connection) -> None:
    staff_cols = _columns_of(conn, "staff")
    if "fte" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN fte REAL")
    booking_cols = _columns_of(conn, "booking")
    if "online_student_count" not in booking_cols:
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN online_student_count INTEGER")


@_migration(15, "Add staff_unit_online_students")
def _m15(conn: Connection) -> None:
    if not _table_exists(conn, "staff_unit_online_students"):
        conn.exec_driver_sql(
            "CREATE TABLE staff_unit_online_students ("
            "staff_id INTEGER NOT NULL, "
            "unit_id INTEGER NOT NULL, "
            "student_count INTEGER, "
            "PRIMARY KEY (staff_id, unit_id), "
            "FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE, "
            "FOREIGN KEY(unit_id) REFERENCES unit(id) ON DELETE CASCADE)"
        )


@_migration(14, "Add staff_qualification_online_students")
def _m14(conn: Connection) -> None:
    if not _table_exists(conn, "staff_qualification_online_students"):
        conn.exec_driver_sql(
            "CREATE TABLE staff_qualification_online_students ("
            "staff_id INTEGER NOT NULL, "
            "qualification_id INTEGER NOT NULL, "
            "student_count INTEGER, "
            "PRIMARY KEY (staff_id, qualification_id), "
            "FOREIGN KEY(staff_id) REFERENCES staff(id) ON DELETE CASCADE, "
            "FOREIGN KEY(qualification_id) REFERENCES qualification(id) ON DELETE CASCADE)"
        )


@_migration(13, "Add staff.development_project_description")
def _m13(conn: Connection) -> None:
    staff_cols = _columns_of(conn, "staff")
    if "development_project_description" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN development_project_description TEXT")


@_migration(12, "Add staff.default_online_students_per_class")
def _m12(conn: Connection) -> None:
    staff_cols = _columns_of(conn, "staff")
    if "default_online_students_per_class" not in staff_cols:
        conn.exec_driver_sql(
            "ALTER TABLE staff ADD COLUMN default_online_students_per_class INTEGER"
        )


@_migration(11, "Add staff OT / development / TAE / supervision hours")
def _m11(conn: Connection) -> None:
    staff_cols = _columns_of(conn, "staff")
    if "ot_hours" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN ot_hours REAL")
    if "development_project_hours" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN development_project_hours REAL")
    if "tae_hours" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN tae_hours REAL")
    if "supervision_hours" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN supervision_hours REAL")


@_migration(9, "Add staff.non_teaching_day and staff_preference table")
def _m9(conn: Connection) -> None:
    staff_cols = _columns_of(conn, "staff")
    if "non_teaching_day" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN non_teaching_day INTEGER")
    if not _table_exists(conn, "staff_preference"):
        conn.exec_driver_sql(
            "CREATE TABLE staff_preference ("
            " id INTEGER PRIMARY KEY,"
            " staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,"
            " priority INTEGER NOT NULL,"
            " slot_number INTEGER NOT NULL,"
            " qualification_name TEXT,"
            " class_name TEXT,"
            " unit_id INTEGER REFERENCES unit(id) ON DELETE SET NULL,"
            " UNIQUE(staff_id, priority, slot_number),"
            " CHECK(priority >= 1 AND priority <= 3),"
            " CHECK(slot_number >= 1 AND slot_number <= 2)"
            ")"
        )


@_migration(19, "Add booking.sfs_co_teacher_staff_id")
def _m19(conn: Connection) -> None:
    cols = _columns_of(conn, "booking")
    if "sfs_co_teacher_staff_id" not in cols:
        conn.exec_driver_sql(
            "ALTER TABLE booking ADD COLUMN sfs_co_teacher_staff_id INTEGER"
            " REFERENCES staff(id) ON DELETE SET NULL"
        )


@_migration(20, "Add booking.sfs_co_teacher_in_term_1 / in_term_2")
def _m20(conn: Connection) -> None:
    cols = _columns_of(conn, "booking")
    if "sfs_co_teacher_in_term_1" not in cols:
        conn.exec_driver_sql(
            "ALTER TABLE booking ADD COLUMN sfs_co_teacher_in_term_1 INTEGER DEFAULT 0"
        )
    if "sfs_co_teacher_in_term_2" not in cols:
        conn.exec_driver_sql(
            "ALTER TABLE booking ADD COLUMN sfs_co_teacher_in_term_2 INTEGER DEFAULT 0"
        )
    conn.exec_driver_sql(
        """
        UPDATE booking
        SET sfs_co_teacher_in_term_1 = in_term_1,
            sfs_co_teacher_in_term_2 = in_term_2
        WHERE sfs_co_teacher_staff_id IS NOT NULL
        """
    )


@_migration(22, "Add booking.session_weeks for per-week session schedule")
def _m22(conn: Connection) -> None:
    cols = _columns_of(conn, "booking")
    if "session_weeks" not in cols:
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN session_weeks TEXT")


@_migration(24, "Add block delivery fields on qualification and booking")
def _m24(conn: Connection) -> None:
    qual_cols = _columns_of(conn, "qualification")
    if "delivery_mode" not in qual_cols:
        conn.exec_driver_sql(
            "ALTER TABLE qualification ADD COLUMN delivery_mode TEXT DEFAULT 'regular'"
        )
        conn.exec_driver_sql(
            "UPDATE qualification SET delivery_mode = 'regular' WHERE delivery_mode IS NULL"
        )
    if "block_week_count" not in qual_cols:
        conn.exec_driver_sql("ALTER TABLE qualification ADD COLUMN block_week_count INTEGER")
    if "block_start_semester_week" not in qual_cols:
        conn.exec_driver_sql(
            "ALTER TABLE qualification ADD COLUMN block_start_semester_week INTEGER"
        )
    booking_cols = _columns_of(conn, "booking")
    if "block_week_index" not in booking_cols:
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN block_week_index INTEGER")


@_migration(25, "Add per-group block settings on course")
def _m25(conn: Connection) -> None:
    course_cols = _columns_of(conn, "course")
    if "block_week_count" not in course_cols:
        conn.exec_driver_sql("ALTER TABLE course ADD COLUMN block_week_count INTEGER")
    if "block_start_semester_week" not in course_cols:
        conn.exec_driver_sql(
            "ALTER TABLE course ADD COLUMN block_start_semester_week INTEGER"
        )
    # Copy qualification defaults onto linked cohort courses for existing block quals.
    conn.exec_driver_sql(
        """
        UPDATE course
        SET block_week_count = (
            SELECT block_week_count FROM qualification q
            WHERE q.id = course.qualification_id
              AND q.delivery_mode = 'block'
              AND q.block_week_count IS NOT NULL
        )
        WHERE qualification_id IS NOT NULL
          AND block_week_count IS NULL
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE course
        SET block_start_semester_week = (
            SELECT block_start_semester_week FROM qualification q
            WHERE q.id = course.qualification_id
              AND q.delivery_mode = 'block'
              AND q.block_start_semester_week IS NOT NULL
        )
        WHERE qualification_id IS NOT NULL
          AND block_start_semester_week IS NULL
        """
    )


@_migration(26, "Separate block cohort courses from regular group courses")
def _m26(conn: Connection) -> None:
    course_cols = _columns_of(conn, "course")
    if "is_block_cohort" not in course_cols:
        conn.exec_driver_sql(
            "ALTER TABLE course ADD COLUMN is_block_cohort INTEGER DEFAULT 0"
        )
        conn.exec_driver_sql(
            "UPDATE course SET is_block_cohort = 0 WHERE is_block_cohort IS NULL"
        )
    # Courses with block bookings are block cohorts.
    conn.exec_driver_sql(
        """
        UPDATE course
        SET is_block_cohort = 1
        WHERE id IN (
            SELECT DISTINCT course_id FROM booking
            WHERE block_week_index IS NOT NULL
        )
        """
    )
    # Block cohorts created with the dedicated naming pattern.
    conn.exec_driver_sql(
        """
        UPDATE course
        SET is_block_cohort = 1
        WHERE is_block_cohort = 0
          AND code LIKE '% Blk Grp%'
        """
    )


@_migration(27, "Re-flag block cohort courses and fix misclassified Blk Grp rows")
def _m27(conn: Connection) -> None:
    conn.exec_driver_sql(
        """
        UPDATE course
        SET is_block_cohort = 1
        WHERE code LIKE '% Blk Grp%'
          AND COALESCE(is_block_cohort, 0) = 0
        """
    )


@_migration(28, "Enable block delivery mode for qualifications with block cohorts")
def _m28(conn: Connection) -> None:
    conn.exec_driver_sql(
        """
        UPDATE qualification
        SET delivery_mode = 'block'
        WHERE id IN (
            SELECT DISTINCT qualification_id FROM course
            WHERE qualification_id IS NOT NULL
              AND (
                  COALESCE(is_block_cohort, 0) = 1
                  OR code LIKE '% Blk Grp%'
              )
        )
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE qualification
        SET block_week_count = COALESCE(block_week_count, 1),
            block_start_semester_week = COALESCE(block_start_semester_week, 1)
        WHERE delivery_mode = 'block'
          AND (block_week_count IS NULL OR block_start_semester_week IS NULL)
        """
    )


@_migration(29, "Add staff.staff_identifier for user-entered Staff ID")
def _m29(conn: Connection) -> None:
    staff_cols = _columns_of(conn, "staff")
    if "staff_identifier" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN staff_identifier TEXT")


@_migration(23, "Normalize room.room_type to on-campus / off-campus / online")
def _m23(conn: Connection) -> None:
    if not _table_exists(conn, "room"):
        return
    conn.exec_driver_sql(
        """
        UPDATE room SET room_type = 'online'
        WHERE lower(trim(coalesce(room_type, ''))) IN ('virtual', 'online')
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE room SET room_type = 'off-campus'
        WHERE lower(trim(coalesce(room_type, ''))) IN ('off campus', 'off-campus')
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE room SET room_type = 'on-campus'
        WHERE room_type IS NULL
           OR trim(room_type) = ''
           OR lower(trim(room_type)) IN ('general', 'on campus', 'on-campus')
        """
    )
    if _table_exists(conn, "unit"):
        conn.exec_driver_sql(
            """
            UPDATE unit SET required_room_type = 'online'
            WHERE lower(trim(coalesce(required_room_type, ''))) IN ('virtual', 'online')
            """
        )
        conn.exec_driver_sql(
            """
            UPDATE unit SET required_room_type = 'off-campus'
            WHERE lower(trim(coalesce(required_room_type, ''))) IN ('off campus', 'off-campus')
            """
        )
        conn.exec_driver_sql(
            """
            UPDATE unit SET required_room_type = 'on-campus'
            WHERE required_room_type IS NOT NULL
              AND lower(trim(required_room_type)) IN ('general', 'on campus', 'on-campus')
            """
        )


@_migration(21, "Add course/staff sidebar_order for timetable SELECT list")
def _m21(conn: Connection) -> None:
    course_cols = _columns_of(conn, "course")
    if "sidebar_order" not in course_cols:
        conn.exec_driver_sql("ALTER TABLE course ADD COLUMN sidebar_order INTEGER DEFAULT 0")
    staff_cols = _columns_of(conn, "staff")
    if "sidebar_order" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN sidebar_order INTEGER DEFAULT 0")
    for index, (cid,) in enumerate(
        conn.exec_driver_sql("SELECT id FROM course ORDER BY id").fetchall()
    ):
        conn.exec_driver_sql(
            "UPDATE course SET sidebar_order = ? WHERE id = ?",
            (index, cid),
        )
    for index, (sid,) in enumerate(
        conn.exec_driver_sql("SELECT id FROM staff ORDER BY name, id").fetchall()
    ):
        conn.exec_driver_sql(
            "UPDATE staff SET sidebar_order = ? WHERE id = ?",
            (index, sid),
        )


@_migration(18, "Add double-session fields on unit and booking.session_part")
def _m18(conn: Connection) -> None:
    unit_cols = _columns_of(conn, "unit")
    if "double_session" not in unit_cols:
        conn.exec_driver_sql("ALTER TABLE unit ADD COLUMN double_session INTEGER DEFAULT 0")
    if "double_session_same_day" not in unit_cols:
        conn.exec_driver_sql("ALTER TABLE unit ADD COLUMN double_session_same_day INTEGER")
    if "double_session_first_slots" not in unit_cols:
        conn.exec_driver_sql("ALTER TABLE unit ADD COLUMN double_session_first_slots INTEGER")
    booking_cols = _columns_of(conn, "booking")
    if "session_part" not in booking_cols:
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN session_part INTEGER DEFAULT 1")


@_migration(17, "Add timetable lock columns on booking, staff, and course")
def _m17(conn: Connection) -> None:
    booking_cols = _columns_of(conn, "booking")
    if "lock_time" not in booking_cols:
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN lock_time INTEGER DEFAULT 0")
    if "lock_staff" not in booking_cols:
        conn.exec_driver_sql("ALTER TABLE booking ADD COLUMN lock_staff INTEGER DEFAULT 0")
    staff_cols = _columns_of(conn, "staff")
    if "timetable_locked" not in staff_cols:
        conn.exec_driver_sql("ALTER TABLE staff ADD COLUMN timetable_locked INTEGER DEFAULT 0")
    course_cols = _columns_of(conn, "course")
    if "timetable_locked" not in course_cols:
        conn.exec_driver_sql("ALTER TABLE course ADD COLUMN timetable_locked INTEGER DEFAULT 0")


@_migration(16, "Add qualification.schedule_period and backfill day windows")
def _m16(conn: Connection) -> None:
    qual_cols = _columns_of(conn, "qualification")
    if "schedule_period" not in qual_cols:
        conn.exec_driver_sql(
            "ALTER TABLE qualification ADD COLUMN schedule_period TEXT DEFAULT 'day'"
        )
        conn.exec_driver_sql(
            "UPDATE qualification SET schedule_period = 'day' WHERE schedule_period IS NULL"
        )
    if not _table_exists(conn, "qualification_time_window"):
        return
    # Backfill standard day windows for qualifications that had no constraint.
    from ..constants import NUM_DAYS, time_to_slot
    from datetime import time

    day_start = time_to_slot(time(8, 30))
    day_end = time_to_slot(time(19, 0))
    quals = conn.exec_driver_sql("SELECT id FROM qualification").fetchall()
    for (qid,) in quals:
        count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM qualification_time_window WHERE qualification_id = ?",
            (qid,),
        ).fetchone()[0]
        if count:
            continue
        for day in range(NUM_DAYS):
            conn.exec_driver_sql(
                "INSERT INTO qualification_time_window "
                "(qualification_id, day, start_slot, end_slot) VALUES (?, ?, ?, ?)",
                (qid, day, day_start, day_end),
            )


@_migration(7, "Add Qualification.num_groups and Course.qualification_id")
def _m7(conn: Connection) -> None:
    qual_cols = _columns_of(conn, "qualification")
    if "num_groups" not in qual_cols:
        conn.exec_driver_sql(
            "ALTER TABLE qualification ADD COLUMN num_groups INTEGER DEFAULT 1"
        )
    course_cols = _columns_of(conn, "course")
    if "qualification_id" not in course_cols:
        conn.exec_driver_sql(
            "ALTER TABLE course ADD COLUMN qualification_id INTEGER"
            " REFERENCES qualification(id) ON DELETE SET NULL"
        )


@_migration(6, "Rebuild unit/qualification to drop legacy 'code' column")
def _m6(conn: Connection) -> None:
    """SQLite cannot DROP COLUMN that participates in UNIQUE constraints, so
    we rebuild the affected tables: create new, copy data, drop old, rename."""
    for table in ("unit", "qualification"):
        if not _table_exists(conn, table):
            continue
        cols = _columns_of(conn, table)
        if "code" not in cols:
            continue
        # Decide what columns the new table should have. We keep everything
        # except `code`; whatever still exists comes through verbatim.
        if table == "unit":
            keep = ["id", "name", "external_id", "length_slots", "units",
                    "required_room_type", "required_capacity"]
        else:  # qualification
            keep = ["id", "name"]
        keep = [c for c in keep if c in cols or c in ("name",)]
        # Build CREATE TABLE for the new shape.
        if table == "unit":
            create_sql = (
                "CREATE TABLE unit_new ("
                " id INTEGER PRIMARY KEY,"
                " name TEXT NOT NULL UNIQUE,"
                " external_id TEXT,"
                " length_slots INTEGER,"
                " units TEXT,"
                " required_room_type TEXT,"
                " required_capacity INTEGER"
                ")"
            )
        else:
            create_sql = (
                "CREATE TABLE qualification_new ("
                " id INTEGER PRIMARY KEY,"
                " name TEXT NOT NULL UNIQUE"
                ")"
            )
        new_table = f"{table}_new"
        conn.exec_driver_sql(create_sql)
        # COALESCE makes sure `name` is populated even if the legacy data only
        # had it under `code`.
        if table == "unit":
            select_cols = (
                "id, COALESCE(NULLIF(name, ''), code) AS name,"
                f" {'external_id' if 'external_id' in cols else 'NULL'},"
                f" {'length_slots' if 'length_slots' in cols else 'NULL'},"
                f" {'units' if 'units' in cols else 'NULL'},"
                f" {'required_room_type' if 'required_room_type' in cols else 'NULL'},"
                f" {'required_capacity' if 'required_capacity' in cols else 'NULL'}"
            )
            conn.exec_driver_sql(
                f"INSERT INTO unit_new (id, name, external_id, length_slots, units,"
                f" required_room_type, required_capacity) SELECT {select_cols} FROM unit"
            )
        else:
            conn.exec_driver_sql(
                "INSERT INTO qualification_new (id, name)"
                " SELECT id, COALESCE(NULLIF(name, ''), code) FROM qualification"
            )
        conn.exec_driver_sql(f"DROP TABLE {table}")
        conn.exec_driver_sql(f"ALTER TABLE {new_table} RENAME TO {table}")


# ---- Runner ----

def _ensure_version_table(conn: Connection) -> None:
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    row = conn.exec_driver_sql("SELECT version FROM schema_version").fetchone()
    if row is None:
        # Brand-new DB: the SQLAlchemy create_all run before us has produced a
        # schema that already matches the latest migration, so stamp head.
        # (This will be over-written below if any migrations need to apply.)
        conn.exec_driver_sql("INSERT INTO schema_version (version) VALUES (0)")


def _current_version(conn: Connection) -> int:
    row = conn.exec_driver_sql("SELECT version FROM schema_version").fetchone()
    return int(row[0]) if row else 0


def _set_version(conn: Connection, version: int) -> None:
    conn.exec_driver_sql("UPDATE schema_version SET version = ?", (version,))


def apply_migrations(engine: Engine) -> list[tuple[int, str]]:
    """Apply any pending migrations. Returns a list of (version, description)
    that were run."""
    MIGRATIONS.sort(key=lambda m: m[0])
    applied: list[tuple[int, str]] = []
    with engine.begin() as conn:
        _ensure_version_table(conn)
        cur = _current_version(conn)
        for version, description, fn in MIGRATIONS:
            if version <= cur:
                continue
            fn(conn)
            _set_version(conn, version)
            applied.append((version, description))
    return applied


def head_version() -> int:
    return max((m[0] for m in MIGRATIONS), default=0)

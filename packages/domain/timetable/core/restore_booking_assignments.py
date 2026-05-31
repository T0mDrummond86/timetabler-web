"""Restore lecturer/class/room assignments from a donor SQLite session."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def restore_booking_assignments_from_donor(
    target_db: Path | str,
    donor_db: Path | str,
) -> tuple[int, int]:
    """Copy ``staff_id``, ``unit_id``, and ``room_id`` onto target bookings.

    Bookings are matched by course code, day, start/end slot, and session part.
    Returns ``(updated_count, unmatched_target_count)``.
    """
    target_db = Path(target_db)
    donor_db = Path(donor_db)
    tgt = sqlite3.connect(target_db)
    don = sqlite3.connect(donor_db)
    try:
        tgt.row_factory = sqlite3.Row
        don.row_factory = sqlite3.Row

        def load_map(conn: sqlite3.Connection) -> dict[tuple, tuple[int | None, int | None, int | None]]:
            rows = conn.execute(
                """
                SELECT c.code, b.day, b.start_slot, b.end_slot, b.session_part,
                       b.staff_id, b.unit_id, b.room_id
                FROM booking b
                JOIN course c ON c.id = b.course_id
                """
            ).fetchall()
            out: dict[tuple, tuple[int | None, int | None, int | None]] = {}
            for r in rows:
                key = (r["code"], int(r["day"]), int(r["start_slot"]), int(r["end_slot"]), int(r["session_part"] or 1))
                out[key] = (r["staff_id"], r["unit_id"], r["room_id"])
            return out

        donor_map = load_map(don)
        target_rows = tgt.execute(
            """
            SELECT b.id, c.code, b.day, b.start_slot, b.end_slot, b.session_part
            FROM booking b
            JOIN course c ON c.id = b.course_id
            """
        ).fetchall()

        updated = 0
        unmatched = 0
        for r in target_rows:
            key = (r["code"], int(r["day"]), int(r["start_slot"]), int(r["end_slot"]), int(r["session_part"] or 1))
            donor_vals = donor_map.get(key)
            if donor_vals is None:
                unmatched += 1
                continue
            staff_id, unit_id, room_id = donor_vals
            tgt.execute(
                """
                UPDATE booking
                SET staff_id = ?, unit_id = ?, room_id = ?
                WHERE id = ?
                """,
                (staff_id, unit_id, room_id, r["id"]),
            )
            updated += 1
        tgt.commit()
        return updated, unmatched
    finally:
        tgt.close()
        don.close()

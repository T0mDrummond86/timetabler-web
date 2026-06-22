#!/usr/bin/env python3
"""Re-run combined-class detection on existing timetable sessions (no re-import).

Usage (Docker):
  docker compose exec api python backend/scripts/reapply_combined_classes.py
  docker compose exec api python backend/scripts/reapply_combined_classes.py --session-id 3

Usage (local API env):
  cd backend && python scripts/reapply_combined_classes.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python backend/scripts/...` from repo root or /app in Docker.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import get_session_factory  # noqa: E402
from app.services.violation_cache import invalidate_session_violations  # noqa: E402
from timetable.core.combined_class import apply_combined_class_detection  # noqa: E402
from timetable.core.tenancy_models import TimetableSession  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-id",
        type=int,
        default=None,
        help="Only process this timetable session id (default: all sessions)",
    )
    args = parser.parse_args()

    db = get_session_factory()()
    try:
        q = db.query(TimetableSession).order_by(TimetableSession.id)
        if args.session_id is not None:
            q = q.filter(TimetableSession.id == args.session_id)
        sessions = q.all()
        if not sessions:
            print("No matching timetable sessions.", file=sys.stderr)
            return 1

        for row in sessions:
            n_groups, n_bookings = apply_combined_class_detection(db, row.id)
            db.commit()
            invalidate_session_violations(db, row.id)
            print(
                f"Session {row.id} ({row.name!r}): "
                f"{n_groups} combined class group(s), {n_bookings} booking(s) tagged"
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

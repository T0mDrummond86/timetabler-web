"""Staff sidebar entity list performance and correctness."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DOMAIN = BACKEND.parent / "packages" / "domain"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(DOMAIN))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")

from timetable.core.models import Staff  # noqa: E402

from app.services import timetable_entities  # noqa: E402


def test_staff_entities_uses_batch_hours_map(monkeypatch: pytest.MonkeyPatch) -> None:
    staff = [
        Staff(id=1, name="Alice", timetable_session_id=10),
        Staff(id=2, name="Bob", timetable_session_id=10),
    ]
    calls: list[int] = []

    def fake_ordered(_db):
        return staff

    def fake_map(_db, timetable_session_id: int, *, staff_rows=None):
        calls.append(len(staff_rows or []))
        return {s.id: float(s.id) for s in (staff_rows or [])}

    monkeypatch.setattr(timetable_entities, "ordered_staff", fake_ordered)
    monkeypatch.setattr(
        timetable_entities,
        "staff_tab_total_hours_map_for_session",
        fake_map,
    )

    rows = timetable_entities._staff_entities(MagicMock(), 10)
    assert calls == [2]
    assert [r["label"] for r in rows] == ["Alice  ·  1.0 h", "Bob  ·  2.0 h"]

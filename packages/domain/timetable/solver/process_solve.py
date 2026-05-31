"""Run auto-timetable in a child process (kill on cancel)."""
from __future__ import annotations

import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..core.auto_timetable_constraints import AutoTimetableConstraintSettings

from .solver import SolveReport


def run_auto_solve_in_process(
    session_name: str,
    week_id: int,
    movable_ids: list[int] | None,
    settings: "AutoTimetableConstraintSettings",
    *,
    time_limit_s: float,
    db_path: str | Path | None = None,
) -> SolveReport:
    """Open a fresh DB session and run :func:`solve_auto_timetable` (same process or child)."""
    from sqlalchemy.orm import sessionmaker

    from ..core.storage import make_engine
    from .auto_solve import solve_auto_timetable

    if db_path is not None:
        eng = make_engine(db_path)
    else:
        eng = make_engine(session_name=session_name)
    try:
        Session = sessionmaker(bind=eng, expire_on_commit=False)
        with Session() as session:
            return solve_auto_timetable(
                session,
                week_id,
                movable_ids,
                settings,
                time_limit_s=time_limit_s,
            )
    finally:
        eng.dispose()


def _auto_solve_subprocess_entry(
    result_queue: Any,
    session_name: str,
    week_id: int,
    movable_ids: list[int] | None,
    settings: "AutoTimetableConstraintSettings",
    time_limit_s: float,
    db_path: str | None = None,
) -> None:
    """``multiprocessing.Process`` target — must stay Qt-free (no PySide6 imports)."""
    try:
        rep = run_auto_solve_in_process(
            session_name,
            week_id,
            movable_ids,
            settings,
            time_limit_s=time_limit_s,
            db_path=db_path,
        )
        result_queue.put(("ok", rep))
    except Exception:
        result_queue.put(("err", traceback.format_exc()))


def parse_queue_result(
    kind: str, payload: Any, *, process: Any
) -> SolveReport:
    """Turn a queue message into a :class:`SolveReport` or raise."""
    if kind == "ok":
        return payload
    if kind == "err":
        raise RuntimeError(str(payload))
    raise RuntimeError(
        f"Auto-timetable process returned unexpected message {kind!r} "
        f"(exit code {process.exitcode})"
    )


def cancelled_report() -> SolveReport:
    return SolveReport(
        status="UNKNOWN",
        moves=[],
        objective=None,
        seconds=0.0,
        solve_pass="failed",
        failure_hints=("Cancelled.",),
    )

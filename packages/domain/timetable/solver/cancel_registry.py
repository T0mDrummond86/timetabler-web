"""Cooperative cancellation for long CP-SAT runs (auto-timetable)."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


class SolverCancelRegistry:
    """Track active ``CpSolver`` instances so the UI can call ``StopSearch()``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._solvers: list[object] = []
        self._stop_requested = threading.Event()

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    def register(self, solver: object) -> None:
        with self._lock:
            self._solvers.append(solver)

    def unregister(self, solver: object) -> None:
        with self._lock:
            try:
                self._solvers.remove(solver)
            except ValueError:
                pass

    def request_stop(self) -> None:
        """Signal cancel and stop any in-flight CP-SAT search."""
        self._stop_requested.set()
        self.stop_all()

    def clear_stop_requested(self) -> None:
        self._stop_requested.clear()

    def reset(self) -> None:
        """Clear cancel state after a run finishes (worker thread must be done)."""
        self._stop_requested.clear()
        with self._lock:
            self._solvers.clear()

    def stop_all(self) -> None:
        # Never call StopSearch while holding _lock — the worker thread unregisters
        # in the same finally block as Solve() returns, and needs that lock.
        with self._lock:
            solvers = list(self._solvers)
        for solver in solvers:
            try:
                solver.StopSearch()  # type: ignore[attr-defined]
            except Exception:
                pass


solve_cancel_registry = SolverCancelRegistry()


@contextmanager
def registered_solver(solver: object) -> Iterator[None]:
    solve_cancel_registry.register(solver)
    try:
        yield
    finally:
        solve_cancel_registry.unregister(solver)

"""Staff availability constraints: hard blocked times, soft non-teaching day."""
from __future__ import annotations

from ortools.sat.python import cp_model

from ..constants import NUM_DAYS
from ..core.auto_timetable_constraints import PENALTY_NON_TEACHING_DAY


def non_teaching_day_penalty_terms(
    model: cp_model.CpModel,
    *,
    movable: list,
    staff_all: dict[int, object],
    staff_presence: dict[int, dict[int | None, cp_model.IntVar]],
    day_var: dict[int, cp_model.IntVar],
) -> list:
    """Medium penalty when a lecturer is assigned on their non-teaching day."""
    terms: list = []
    for b in movable:
        for sid, pres in staff_presence[b.id].items():
            if sid is None:
                continue
            staff = staff_all.get(sid)
            if staff is None:
                continue
            nt = getattr(staff, "non_teaching_day", None)
            if nt is None or not (0 <= nt < NUM_DAYS):
                continue
            on_nt = model.NewBoolVar(f"ntday_{b.id}_{sid}")
            model.Add(day_var[b.id] == nt).OnlyEnforceIf(on_nt)
            model.Add(day_var[b.id] != nt).OnlyEnforceIf(on_nt.Not())
            viol = model.NewBoolVar(f"ntviol_{b.id}_{sid}")
            model.Add(viol <= pres)
            model.Add(viol <= on_nt)
            model.Add(viol >= pres + on_nt - 1)
            terms.append(PENALTY_NON_TEACHING_DAY * viol)
    return terms

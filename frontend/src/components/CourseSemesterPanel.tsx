import type { CourseSemesterSchedule } from "../types";

type Props = {
  schedule: CourseSemesterSchedule | null;
  loading?: boolean;
  onSelectWeek: (week: number) => void;
  onToggleWeek: (bookingId: number, week: number) => void;
};

export function CourseSemesterPanel({
  schedule,
  loading,
  onSelectWeek,
  onToggleWeek,
}: Props) {
  if (loading) {
    return (
      <section className="panel semester-panel">
        <div className="panel-body muted">Loading semester schedule…</div>
      </section>
    );
  }
  if (!schedule) return null;

  const weekHeaders = Array.from({ length: schedule.semester_weeks }, (_, i) => i + 1);

  return (
    <section className="panel semester-panel">
      <div className="panel-header">
        <h2>
          Semester weeks — {schedule.course_code} (W{schedule.selected_semester_week} selected)
        </h2>
      </div>
      <div className="panel-body semester-scroll">
        <table className="semester-table">
          <thead>
            <tr>
              <th className="semester-label-col">Class / time</th>
              {weekHeaders.map((w) => (
                <th
                  key={w}
                  className={`semester-week-col${w <= 10 ? " term1" : " term2"}${w === schedule.selected_semester_week ? " selected" : ""}`}
                >
                  {w === 1 ? "T1 W1" : w === 11 ? "T2 W11" : `W${w}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {schedule.rows.map((row) => (
              <tr key={row.primary_booking_id}>
                <td className="semester-label-col" title={row.has_variants ? "Alternate schedules in some weeks" : undefined}>
                  {row.label}
                </td>
                {row.weeks.map((cell) => {
                  let cls = "semester-cell";
                  if (!cell.applicable) cls += " na";
                  else if (cell.active) cls += " active";
                  if (cell.week === schedule.selected_semester_week) cls += " selected-col";
                  return (
                    <td key={cell.week} className={cls}>
                      <button
                        type="button"
                        className="semester-cell-btn"
                        title={
                          cell.applicable
                            ? cell.active
                              ? `Week ${cell.week}: active — click to edit below; right-click toggles`
                              : `Week ${cell.week}: inactive — click to select; right-click to add`
                            : "Not applicable for this booking"
                        }
                        onClick={() => onSelectWeek(cell.week)}
                        onContextMenu={(e) => {
                          e.preventDefault();
                          if (cell.applicable) onToggleWeek(cell.booking_id, cell.week);
                        }}
                      >
                        {cell.active ? "●" : ""}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="semester-hint muted">
          Click a week cell to edit that week in the timetable below. Right-click to add or remove
          that session. Green = class runs that week. Term 1: weeks 1–10 · Term 2: weeks 11–20.
        </p>
      </div>
    </section>
  );
}

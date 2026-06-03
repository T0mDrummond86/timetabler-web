import { useState } from "react";
import type { BlockOverview, BlockWeekUsage } from "../types";

type Props = {
  overview: BlockOverview | null;
  loading?: boolean;
  onLoadUsage: (courseId: number, semesterWeek: number) => Promise<BlockWeekUsage | null>;
};

export function BlockOverviewView({ overview, loading, onLoadUsage }: Props) {
  const [usage, setUsage] = useState<BlockWeekUsage | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);

  if (loading) {
    return (
      <section className="panel">
        <div className="panel-body muted">Loading block overview…</div>
      </section>
    );
  }
  if (!overview) return null;

  const weekHeaders = Array.from({ length: overview.semester_weeks }, (_, i) => i + 1);

  async function onCellClick(courseId: number, week: number, active: boolean) {
    if (!active) return;
    setUsageLoading(true);
    try {
      const grid = await onLoadUsage(courseId, week);
      setUsage(grid);
    } finally {
      setUsageLoading(false);
    }
  }

  return (
    <div className="block-overview-stack">
      <section className="panel semester-panel">
        <div className="panel-header">
          <h2>Block groups — semester overview</h2>
        </div>
        <div className="panel-body semester-scroll">
          {overview.rows.length === 0 ? (
            <p className="muted">No block cohort groups in this session.</p>
          ) : (
            <table className="semester-table block-overview-table">
              <thead>
                <tr>
                  <th className="semester-label-col">Block group</th>
                  {weekHeaders.map((w) => (
                    <th
                      key={w}
                      className={`semester-week-col${w <= 10 ? " term1" : " term2"}`}
                    >
                      {w === 1 ? "T1 W1" : w === 11 ? "T2 W11" : `W${w}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {overview.rows.map((row) => (
                  <tr key={row.course_id}>
                    <td className="semester-label-col" title={row.tooltip}>
                      {row.label}
                    </td>
                    {weekHeaders.map((w) => {
                      const active = row.calendar_weeks.includes(w);
                      return (
                        <td key={w} className={`semester-cell${active ? " active" : " na"}`}>
                          {active ? (
                            <button
                              type="button"
                              className="semester-cell-btn"
                              title={`Week ${w}: click for room usage`}
                              onClick={() => void onCellClick(row.course_id, w, true)}
                            >
                              ●
                            </button>
                          ) : null}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="semester-hint muted">
            Green cells show semester weeks when each block group runs — click one to open the
            room usage / clash grid below.
          </p>
        </div>
      </section>

      {(usage || usageLoading) && (
        <section className="panel block-usage-panel">
          <div className="panel-header">
            <h2>{usageLoading ? "Loading usage…" : usage?.title ?? "Room usage"}</h2>
            {usage?.subtitle && <span className="muted">{usage.subtitle}</span>}
          </div>
          {usage && (
            <div className="panel-body semester-scroll">
              <table className="block-usage-table">
                <thead>
                  <tr>
                    <th>Day</th>
                    {usage.rooms.map((r) => (
                      <th key={r}>{r}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {usage.days.map((day, dayIdx) => (
                    <tr key={day}>
                      <th>{day}</th>
                      {usage.rooms.map((_, roomIdx) => {
                        const cell = usage.cells[dayIdx]?.[roomIdx];
                        const status = cell?.status ?? "empty";
                        return (
                          <td
                            key={`${dayIdx}-${roomIdx}`}
                            className={`usage-cell status-${status}`}
                            title={cell?.tooltip ?? ""}
                          >
                            {cell?.label ?? ""}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

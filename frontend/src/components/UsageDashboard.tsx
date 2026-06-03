import { Fragment } from "react";
import { useCallback, useEffect, useState } from "react";
import { slotToTimeLabel } from "../lib/timeUtils";
import { api } from "../api";
import type { ResourceUsage } from "../types";

type Props = {
  sessionId: number;
  refreshKey?: number;
};

export function UsageDashboard({ sessionId, refreshKey = 0 }: Props) {
  const [kind, setKind] = useState<"staff" | "room">("staff");
  const [data, setData] = useState<ResourceUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(kind === "staff" ? await api.staffUsage(sessionId) : await api.roomUsage(sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load usage");
    } finally {
      setLoading(false);
    }
  }, [sessionId, kind]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <section className="panel usage-dashboard">
      <div className="panel-header usage-dashboard-header">
        <h2>Resource usage</h2>
        <div className="usage-dashboard-controls">
          <select className="field-select" value={kind} onChange={(e) => setKind(e.target.value as "staff" | "room")}>
            <option value="staff">Lecturer usage</option>
            <option value="room">Room usage</option>
          </select>
          <button type="button" className="btn-secondary" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>
      <div className="panel-body">
        {error && <p className="error">{error}</p>}
        {loading && !data && <p className="muted">Loading…</p>}
        {data && (
          <>
            <p className="violations-summary">{data.summary}</p>
            {!data.resources.length ? (
              <p className="muted">No resources in this session.</p>
            ) : (
              <div className="usage-table-scroll">
                <table className="usage-table">
                  <thead>
                    <tr>
                      <th className="usage-time-col">Time</th>
                      {data.resources.map((label, i) => (
                        <th key={data.resource_ids[i]} title={data.resource_tooltips[i]}>
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.days.map((dayLabel, dayIdx) => (
                      <Fragment key={dayLabel}>
                        <tr className="usage-day-banner">
                          <td colSpan={data.resources.length + 1}>{dayLabel}</td>
                        </tr>
                        {Array.from({ length: data.num_slots }, (_, slot) => {
                          const row = data.cells[dayIdx]?.[slot] ?? [];
                          const timeLabel = slot % 2 === 0 ? slotToTimeLabel(slot) : "";
                          return (
                            <tr key={`${dayIdx}-${slot}`}>
                              <td className="usage-time-col">{timeLabel}</td>
                              {row.map((cell, colIdx) => (
                                <td
                                  key={colIdx}
                                  className={`usage-cell status-${cell.status}`}
                                  style={
                                    cell.fill_colour && cell.status === "busy"
                                      ? { backgroundColor: cell.fill_colour }
                                      : undefined
                                  }
                                  title={cell.tooltip || undefined}
                                >
                                  {cell.label}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

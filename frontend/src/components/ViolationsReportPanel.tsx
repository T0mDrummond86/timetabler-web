import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ViolationRow, ViolationsReport } from "../types";

type Props = {
  sessionId: number;
  refreshKey?: number;
  onGoToBooking?: (bookingId: number, row: ViolationRow) => void;
};

function columnHasValues(rows: ViolationRow[], key: string): boolean {
  return rows.some((r) => String(r[key] ?? "").trim() !== "");
}

export function ViolationsReportPanel({ sessionId, refreshKey = 0, onGoToBooking }: Props) {
  const [severity, setSeverity] = useState<string>("");
  const [report, setReport] = useState<ViolationsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.violationsReport(
        sessionId,
        severity === "" ? undefined : (severity as "hard" | "soft"),
      );
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load warnings");
    } finally {
      setLoading(false);
    }
  }, [sessionId, severity]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const visibleHeaders = useMemo(() => {
    if (!report) return [];
    return report.headers.filter((h) => {
      if (h === "ID" && !columnHasValues(report.rows, "ID")) return false;
      return true;
    });
  }, [report]);

  const displayRows = useMemo(() => {
    if (!report?.rows.length) return [];
    return [...report.rows].sort((a, b) => {
      const sev =
        (a.severity === "hard" ? 0 : 1) - (b.severity === "hard" ? 0 : 1);
      if (sev !== 0) return sev;
      const desc = String(a.description ?? "").localeCompare(String(b.description ?? ""));
      if (desc !== 0) return desc;
      return String(a.group ?? "").localeCompare(String(b.group ?? ""));
    });
  }, [report]);

  return (
    <section className="panel violations-report-panel">
      <div className="panel-header violations-report-header">
        <h2>Warnings</h2>
        <div className="violations-report-controls">
          <label>
            Show
            <select
              className="field-select"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              <option value="">All warnings</option>
              <option value="hard">Hard (clashes / blocks) only</option>
              <option value="soft">Soft warnings only</option>
            </select>
          </label>
          <button type="button" className="btn-secondary" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>
      <div className="panel-body">
        {error && <p className="error">{error}</p>}
        {loading && !report && <p className="muted">Loading…</p>}
        {report && (
          <>
            <p className="violations-summary">{report.summary}</p>
            {onGoToBooking && (
              <p className="muted violations-hint">Click a row to open that booking on the timetable.</p>
            )}
            {!report.rows.length ? (
              <p className="muted">No warnings for the current week.</p>
            ) : (
              <div className="violations-table-scroll">
                <table className="violations-table">
                  <thead>
                    <tr>
                      {visibleHeaders.map((h) => (
                        <th key={h}>{h === "severity" ? "Severity" : h}</th>
                      ))}
                      {onGoToBooking && <th className="violations-go-col"> </th>}
                    </tr>
                  </thead>
                  <tbody>
                    {displayRows.map((row, i) => {
                      const bookingId = row.booking_ids?.[0];
                      const clickable = Boolean(onGoToBooking && bookingId != null);
                      return (
                        <tr
                          key={i}
                          className={[
                            row.severity === "hard" ? "hard" : "soft",
                            clickable ? "violations-row-clickable" : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          onClick={
                            clickable
                              ? () => onGoToBooking!(bookingId!, row)
                              : undefined
                          }
                          onKeyDown={
                            clickable
                              ? (e) => {
                                  if (e.key === "Enter" || e.key === " ") {
                                    e.preventDefault();
                                    onGoToBooking!(bookingId!, row);
                                  }
                                }
                              : undefined
                          }
                          tabIndex={clickable ? 0 : undefined}
                          role={clickable ? "button" : undefined}
                        >
                          {visibleHeaders.map((h) => (
                            <td key={h}>{row[h] ?? ""}</td>
                          ))}
                          {onGoToBooking && (
                            <td className="violations-go-col">
                              {clickable ? (
                                <span className="violations-go-link">Open</span>
                              ) : (
                                ""
                              )}
                            </td>
                          )}
                        </tr>
                      );
                    })}
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

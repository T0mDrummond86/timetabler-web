import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { ChangeLogRow } from "../types";

const ACTION_COLOURS: Record<string, string> = {
  change: "#0c4a6e",
  undo: "#9a3412",
  redo: "#854d0e",
  net: "#14532d",
};

type Props = {
  sessionId: number;
  resolveCourseId: (bookingId?: number) => number | null;
  refreshKey?: number;
  onRollback?: () => void;
};

export function ChangeLogPanel({ sessionId, resolveCourseId, refreshKey = 0, onRollback }: Props) {
  const [resolved, setResolved] = useState(false);
  const [rows, setRows] = useState<ChangeLogRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingNote, setSavingNote] = useState<number | null>(null);
  const [rollingBack, setRollingBack] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.changeLog(sessionId, resolved);
      setRows(data.rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load change log");
    } finally {
      setLoading(false);
    }
  }, [sessionId, resolved]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  async function saveNote(entryId: number, bookingId: number, note: string) {
    setSavingNote(bookingId);
    try {
      await api.setChangeLogNote(sessionId, entryId, { booking_id: bookingId, note });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save note");
    } finally {
      setSavingNote(null);
    }
  }

  async function rollback(bookingId: number) {
    const cid = resolveCourseId(bookingId);
    if (!cid) {
      setError("Could not determine course for rollback.");
      return;
    }
    if (!window.confirm("Roll this booking back to its earliest logged state?")) return;
    setRollingBack(bookingId);
    setError(null);
    try {
      await api.rollbackChangeLog(sessionId, { booking_id: bookingId, course_id: cid });
      onRollback?.();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rollback failed");
    } finally {
      setRollingBack(null);
    }
  }

  const emptyMessage = resolved
    ? "(no net changes — schedule matches the earliest state in this session's log)"
    : "(no timetabling changes yet — moves and edits on the week grid appear here)";

  const showIdColumn = rows.some((r) => String(r.row.id ?? "").trim() !== "");
  const showDelColumn = rows.some((r) => String(r.row.delete ?? "").trim() !== "");

  return (
    <section className="panel">
      <div className="change-log-toolbar">
        <h2>Change log</h2>
        <button type="button" className="btn-secondary" onClick={() => void load()} disabled={loading}>
          Refresh
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setResolved((v) => !v)}
          title="Collapse intermediate edits into a single net change per booking"
        >
          {resolved ? "Full log" : "Resolved"}
        </button>
        {resolved && (
          <button type="button" className="btn-secondary" onClick={() => void api.exportChangeLog(sessionId)}>
            Export
          </button>
        )}
      </div>

      {error && <div className="error-banner" style={{ margin: "0 1rem 0.75rem" }}>{error}</div>}
      {loading && <p className="panel-empty">Loading change log…</p>}

      {!loading && (
        <div className="change-log-table-wrap">
          <table className="change-log-table">
            <thead>
              <tr>
                {showIdColumn && <th>Card ID</th>}
                <th>Group</th>
                <th>Class</th>
                <th>Lecturer</th>
                <th>Time</th>
                <th>Day</th>
                <th>Room</th>
                {showDelColumn && <th>Removed</th>}
                <th>When</th>
                <th>Action</th>
                {resolved && <th>Notes</th>}
                {resolved && <th>Rollback</th>}
              </tr>
            </thead>
            <tbody>
              {!rows.length && (
                <tr>
                  <td
                    colSpan={
                      (showIdColumn ? 1 : 0) +
                      6 +
                      (showDelColumn ? 1 : 0) +
                      2 +
                      (resolved ? 2 : 0)
                    }
                    className="muted empty-cell"
                  >
                    {emptyMessage}
                  </td>
                </tr>
              )}
              {rows.map((r, idx) => {
                const actionColour = ACTION_COLOURS[r.action] ?? "#444";
                return (
                  <tr key={`${r.entry_id}-${r.booking_id}-${idx}`}>
                    {showIdColumn && <td>{r.row.id ?? ""}</td>}
                    <td>{r.row.group ?? ""}</td>
                    <td>{r.row.class ?? ""}</td>
                    <td>{r.row.lecturer_change ?? ""}</td>
                    <td>{r.row.time_change ?? ""}</td>
                    <td>{r.row.day_change ?? ""}</td>
                    <td>{r.row.room_change ?? ""}</td>
                    {showDelColumn && <td>{r.row.delete ?? ""}</td>}
                    <td>{r.when ?? ""}</td>
                    <td style={{ color: actionColour, fontWeight: 700 }}>{r.action}</td>
                    {resolved && (
                      <td>
                        {r.entry_id != null && r.booking_id != null ? (
                          <input
                            className="note-input"
                            defaultValue={r.note}
                            placeholder="Add note…"
                            disabled={savingNote === r.booking_id}
                            onBlur={(e) =>
                              void saveNote(r.entry_id!, r.booking_id!, e.target.value)
                            }
                          />
                        ) : (
                          ""
                        )}
                      </td>
                    )}
                    {resolved && (
                      <td>
                        {r.booking_id != null ? (
                          <button
                            type="button"
                            className="btn-secondary"
                            style={{ fontSize: "0.78rem", padding: "0.3rem 0.55rem" }}
                            disabled={rollingBack === r.booking_id}
                            onClick={() => void rollback(r.booking_id!)}
                          >
                            {rollingBack === r.booking_id ? "…" : "Rollback"}
                          </button>
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
    </section>
  );
}

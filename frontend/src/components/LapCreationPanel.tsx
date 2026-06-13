import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { LapRow } from "../types";
import { LoadingMark } from "./LoadingMark";

type Props = {
  sessionId: number;
  refreshKey?: number;
};

function lapDeliveryPeriodKey(sessionId: number) {
  return `lap-delivery-period-${sessionId}`;
}

export function LapCreationPanel({ sessionId, refreshKey = 0 }: Props) {
  const [rows, setRows] = useState<LapRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyUnitId, setBusyUnitId] = useState<number | null>(null);
  const [filter, setFilter] = useState("");
  const [deliveryPeriod, setDeliveryPeriod] = useState(() => {
    try {
      return localStorage.getItem(lapDeliveryPeriodKey(sessionId)) ?? "";
    } catch {
      return "";
    }
  });
  const uploadRef = useRef<HTMLInputElement>(null);
  const [uploadUnitId, setUploadUnitId] = useState<number | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(lapDeliveryPeriodKey(sessionId), deliveryPeriod);
    } catch {
      /* ignore quota / private mode */
    }
  }, [sessionId, deliveryPeriod]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.lapList(sessionId);
      setRows(data.rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load LAPs");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const filtered = rows.filter((row) => {
    const q = filter.trim().toLowerCase();
    if (!q) return true;
    return (
      row.unit_name.toLowerCase().includes(q) ||
      (row.component_codes ?? "").toLowerCase().includes(q) ||
      row.timetable_lecturer_name.toLowerCase().includes(q)
    );
  });

  const withLap = rows.filter((r) => r.has_lap).length;

  function pickUpload(unitId: number) {
    setUploadUnitId(unitId);
    uploadRef.current?.click();
  }

  async function onFileSelected(file: File | undefined) {
    if (!file || uploadUnitId == null) return;
    setBusyUnitId(uploadUnitId);
    setError(null);
    try {
      await api.lapUpload(sessionId, uploadUnitId, file);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusyUnitId(null);
      setUploadUnitId(null);
      if (uploadRef.current) uploadRef.current.value = "";
    }
  }

  async function onDownload(unitId: number) {
    setBusyUnitId(unitId);
    setError(null);
    try {
      api.lapDownload(sessionId, unitId, deliveryPeriod);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setBusyUnitId(null);
    }
  }

  async function onDownloadAll() {
    setBusyUnitId(-1);
    setError(null);
    try {
      api.lapDownloadAll(sessionId, deliveryPeriod);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setBusyUnitId(null);
    }
  }

  async function onRemove(unitId: number) {
    if (!window.confirm("Remove the uploaded LAP for this class?")) return;
    setBusyUnitId(unitId);
    setError(null);
    try {
      await api.lapDelete(sessionId, unitId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remove failed");
    } finally {
      setBusyUnitId(null);
    }
  }

  return (
    <section className="panel lap-panel">
      <div className="panel-header">
        <div>
          <h2>LAP creation</h2>
        </div>
        <div className="row gap lap-panel-actions">
          <label className="lap-delivery-period-field">
            <span className="lap-delivery-period-label">Delivery period</span>
            <input
              type="text"
              className="field-input lap-delivery-period-input"
              placeholder="e.g. 2026 Semester 1"
              value={deliveryPeriod}
              onChange={(e) => setDeliveryPeriod(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="btn-secondary"
            disabled={withLap === 0 || busyUnitId !== null}
            onClick={() => void onDownloadAll()}
          >
            Download all updated
          </button>
        </div>
      </div>
      <input
        ref={uploadRef}
        type="file"
        accept=".docx"
        hidden
        onChange={(e) => void onFileSelected(e.target.files?.[0])}
      />
      {error && <p className="error">{error}</p>}
      <div className="lap-toolbar">
        <input
          type="search"
          className="lap-filter"
          placeholder="Filter classes…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <span className="muted">
          {withLap} of {rows.length} classes have a LAP uploaded
        </span>
      </div>
      {loading ? (
        <LoadingMark label="Loading…" />
      ) : (
        <div className="table-wrap">
          <table className="data-table lap-table">
            <thead>
              <tr>
                <th>Class</th>
                <th>Units of study</th>
                <th>Timetable lecturer</th>
                <th>Uploaded LAP</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.unit_id}>
                  <td>{row.unit_name}</td>
                  <td className="muted">{row.component_codes || "—"}</td>
                  <td>{row.timetable_lecturer_name || "—"}</td>
                  <td>
                    {row.has_lap ? (
                      <span title={row.uploaded_at ?? undefined}>{row.original_filename}</span>
                    ) : (
                      <span className="muted">None</span>
                    )}
                  </td>
                  <td className="lap-actions">
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      disabled={busyUnitId !== null}
                      onClick={() => pickUpload(row.unit_id)}
                    >
                      {row.has_lap ? "Replace" : "Upload"}
                    </button>
                    {row.has_lap && (
                      <>
                        <button
                          type="button"
                          className="btn-secondary btn-sm"
                          disabled={busyUnitId !== null || !row.timetable_lecturer_name}
                          title={
                            row.timetable_lecturer_name
                              ? "Download LAP with updated lecturer name"
                              : "Assign a lecturer on the timetable first"
                          }
                          onClick={() => void onDownload(row.unit_id)}
                        >
                          Download updated
                        </button>
                        <button
                          type="button"
                          className="btn-secondary btn-sm"
                          disabled={busyUnitId !== null}
                          onClick={() => void onRemove(row.unit_id)}
                        >
                          Remove
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

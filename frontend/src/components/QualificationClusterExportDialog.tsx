import { useEffect, useMemo, useState } from "react";
import { api, type Qualification } from "../api";

type Props = {
  sessionId: number;
  onClose: () => void;
  onError?: (message: string) => void;
};

/** Select qualifications and download a workbook with one tab per qualification
 *  (cluster name in column A, associated units in column B). */
export function QualificationClusterExportDialog({ sessionId, onClose, onError }: Props) {
  const [quals, setQuals] = useState<Qualification[]>([]);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const rows = await api.qualifications(sessionId);
        if (cancelled) return;
        setQuals(rows);
        setChecked(new Set(rows.map((q) => q.id)));
      } catch (err) {
        if (!cancelled) onError?.(err instanceof Error ? err.message : "Failed to load qualifications");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, onError]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? quals.filter((x) => x.name.toLowerCase().includes(q)) : quals;
  }, [quals, filter]);

  function toggle(id: number) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function download() {
    const ids = [...checked];
    if (ids.length === 0) {
      onError?.("Select at least one qualification");
      return;
    }
    setGenerating(true);
    try {
      await api.downloadExport(
        `/sessions/${sessionId}/export/qualification-clusters?qualification_ids=${ids.join(",")}`,
        "qualification_clusters.xlsx",
      );
      onClose();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Export failed");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal card"
        role="dialog"
        aria-labelledby="cluster-export-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="cluster-export-title">Export qualification clusters</h2>
        <p className="muted">
          One tab per selected qualification — each cluster (class) with its associated units.
        </p>

        {loading ? (
          <p className="muted">Loading qualifications…</p>
        ) : quals.length === 0 ? (
          <p className="muted">No qualifications in this session.</p>
        ) : (
          <>
            <div className="row gap" style={{ alignItems: "center", margin: "0.5rem 0" }}>
              <input
                type="search"
                className="field-input"
                placeholder="Filter…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                aria-label="Filter qualifications"
              />
              <button
                type="button"
                className="btn-secondary btn-xs"
                onClick={() => setChecked(new Set(quals.map((q) => q.id)))}
              >
                Select all
              </button>
              <button
                type="button"
                className="btn-secondary btn-xs"
                onClick={() => setChecked(new Set())}
              >
                Clear
              </button>
              <span className="muted">{checked.size} selected</span>
            </div>

            <div className="cluster-export-list">
              {visible.map((q) => (
                <label key={q.id} className="cluster-export-row">
                  <input
                    type="checkbox"
                    checked={checked.has(q.id)}
                    onChange={() => toggle(q.id)}
                  />
                  <span>{q.name}</span>
                </label>
              ))}
            </div>
          </>
        )}

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={generating || checked.size === 0}
            onClick={() => void download()}
          >
            {generating ? "Generating…" : "Download workbook"}
          </button>
        </div>
      </div>
    </div>
  );
}

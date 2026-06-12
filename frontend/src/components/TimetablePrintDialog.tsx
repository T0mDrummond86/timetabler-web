import { useCallback, useEffect, useState } from "react";
import { api, type TimetablePrintEntity, type TimetablePrintKind } from "../api";

type Props = {
  sessionId: number;
  colourByClass: boolean;
  onClose: () => void;
};

const KIND_OPTIONS: { id: TimetablePrintKind; label: string }[] = [
  { id: "course", label: "Courses (class group timetables)" },
  { id: "staff", label: "Staff timetables" },
  { id: "room", label: "Room timetables" },
];

export function TimetablePrintDialog({ sessionId, colourByClass: _colourByClass, onClose }: Props) {
  const [kind, setKind] = useState<TimetablePrintKind>("course");
  const [weekLabel, setWeekLabel] = useState<string | null>(null);
  const [entities, setEntities] = useState<TimetablePrintEntity[]>([]);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [termFilter, setTermFilter] = useState<"all" | "t1" | "t2">("all");
  const [includeIndex, setIncludeIndex] = useState(true);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadInfo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const info = await api.timetablePrintInfo(sessionId, kind);
      setWeekLabel(info.week_label);
      setEntities(info.entities);
      setChecked(new Set(info.entities.map((e) => e.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
      setEntities([]);
      setChecked(new Set());
    } finally {
      setLoading(false);
    }
  }, [sessionId, kind]);

  useEffect(() => {
    void loadInfo();
  }, [loadInfo]);

  function toggle(id: number) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setChecked(new Set(entities.map((e) => e.id)));
  }

  function selectNone() {
    setChecked(new Set());
  }

  async function onGenerate() {
    const selected = entities.filter((e) => checked.has(e.id));
    if (!selected.length) {
      setError("Tick at least one timetable to print.");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      await api.downloadTimetablePrintPdf(sessionId, {
        kind,
        term_filter: termFilter,
        colour_by_class: true,
        include_index: includeIndex,
        entities: selected,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Print failed");
    } finally {
      setGenerating(false);
    }
  }

  const canPrint = weekLabel != null && !loading;

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal card timetable-print-dialog"
        role="dialog"
        aria-labelledby="print-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="print-dialog-title">Print timetables</h2>
        {weekLabel ? (
          <p className="muted">Current week: {weekLabel}</p>
        ) : (
          <p className="error">No week in this session — printing is disabled.</p>
        )}
        <p className="muted timetable-print-hint">
          All timetables are selected by default. Class colours are always used in PDF print so
          each class appears in a distinct fill (matching the &quot;Class colours&quot; display
          setting). Placecards use thin black borders. Use the index page or PDF bookmarks to jump
          between timetables.
        </p>

        <fieldset className="timetable-print-kinds">
          {KIND_OPTIONS.map((opt) => (
            <label key={opt.id} className="radio">
              <input
                type="radio"
                name="print-kind"
                checked={kind === opt.id}
                onChange={() => setKind(opt.id)}
              />
              {opt.label}
            </label>
          ))}
        </fieldset>

        <label className="timetable-print-term">
          Term filter
          <select
            value={termFilter}
            onChange={(e) => setTermFilter(e.target.value as "all" | "t1" | "t2")}
          >
            <option value="all">All terms</option>
            <option value="t1">Term 1 only</option>
            <option value="t2">Term 2 only</option>
          </select>
        </label>

        {entities.length > 1 && (
          <label className="checkbox timetable-print-index">
            <input
              type="checkbox"
              checked={includeIndex}
              onChange={(e) => setIncludeIndex(e.target.checked)}
            />
            Include index page with clickable links
          </label>
        )}

        <div className="timetable-print-list-actions">
          <button type="button" className="btn-secondary" onClick={selectAll} disabled={loading}>
            Select all
          </button>
          <button type="button" className="btn-secondary" onClick={selectNone} disabled={loading}>
            Deselect all
          </button>
        </div>

        {loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <ul className="timetable-print-list">
            {entities.map((e) => (
              <li key={e.id}>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={checked.has(e.id)}
                    onChange={() => toggle(e.id)}
                  />
                  {e.label}
                </label>
              </li>
            ))}
          </ul>
        )}

        {error && <p className="error">{error}</p>}

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={!canPrint || generating}
            onClick={() => void onGenerate()}
          >
            {generating ? "Generating…" : "Download PDF"}
          </button>
        </div>
      </div>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type TimetablePrintEntity, type TimetablePrintKind } from "../api";

type Props = {
  sessionId: number;
  colourByClass: boolean;
  onClose: () => void;
};

const KIND_OPTIONS: { id: TimetablePrintKind; label: string }[] = [
  { id: "course", label: "Courses (class group timetables)" },
  { id: "staff", label: "Staff timetables" },
  { id: "course_staff", label: "Courses and staff" },
  { id: "room", label: "Room timetables" },
];

function entityKey(entity: TimetablePrintEntity, kind: TimetablePrintKind): string {
  if (kind === "course_staff" && entity.entity_kind) {
    return `${entity.entity_kind}:${entity.id}`;
  }
  return String(entity.id);
}

export function TimetablePrintDialog({ sessionId, colourByClass: _colourByClass, onClose }: Props) {
  const [kind, setKind] = useState<TimetablePrintKind>("course");
  const [weekLabel, setWeekLabel] = useState<string | null>(null);
  const [entities, setEntities] = useState<TimetablePrintEntity[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
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
      setChecked(new Set(info.entities.map((e) => entityKey(e, kind))));
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

  const groupedEntities = useMemo(() => {
    if (kind !== "course_staff") {
      return [{ title: null as string | null, items: entities }];
    }
    const courses = entities.filter((e) => e.entity_kind === "course");
    const staff = entities.filter((e) => e.entity_kind === "staff");
    return [
      { title: "Courses", items: courses },
      { title: "Staff", items: staff },
    ].filter((section) => section.items.length > 0);
  }, [entities, kind]);

  function toggle(entity: TimetablePrintEntity) {
    const key = entityKey(entity, kind);
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectAll() {
    setChecked(new Set(entities.map((e) => entityKey(e, kind))));
  }

  function selectNone() {
    setChecked(new Set());
  }

  async function onGenerate() {
    const selected = entities.filter((e) => checked.has(entityKey(e, kind)));
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
        entities: selected.map((e) =>
          kind === "course_staff" && e.entity_kind
            ? { id: e.id, label: e.label, entity_kind: e.entity_kind }
            : { id: e.id, label: e.label },
        ),
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
          <div className="timetable-print-list">
            {groupedEntities.map((section) => (
              <div key={section.title ?? "all"}>
                {section.title && <h3 className="timetable-print-section-title">{section.title}</h3>}
                <ul>
                  {section.items.map((e) => (
                    <li key={entityKey(e, kind)}>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={checked.has(entityKey(e, kind))}
                          onChange={() => toggle(e)}
                        />
                        {e.label}
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
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

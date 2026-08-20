/** Combine two qualifications into a new third one.
 *
 * The mirror of StageSplitDialog, and deliberately much quieter. A split has
 * to be argued with — it rewrites class links and refuses to run once anything
 * is timetabled — whereas a merge only ever adds a record, so the dialog's job
 * is to show what the result will contain and then get out of the way.
 *
 * The one thing worth being loud about is that both sources survive. Users
 * arrive at a button called "Merge" expecting the two to be consumed, so the
 * dialog says otherwise in plain words rather than leaving it to be discovered.
 */
import { useEffect, useMemo, useState } from "react";
import { api, Qualification } from "../api";
import type { QualificationMergePreview } from "../types";

type Props = {
  sessionId: number;
  /** The qualification the dialog was opened from — the left-hand side. */
  qualificationId: number;
  /** Every qualification in the session, to choose the other side from. */
  qualifications: Qualification[];
  onClose: () => void;
  onMerge: (summary: string, newQualificationId: number) => void;
};

export function QualificationMergeDialog({
  sessionId,
  qualificationId,
  qualifications,
  onClose,
  onMerge,
}: Props) {
  const [otherId, setOtherId] = useState<number | "">("");
  const [preview, setPreview] = useState<QualificationMergePreview | null>(null);
  const [name, setName] = useState("");
  const [numGroups, setNumGroups] = useState(1);
  const [period, setPeriod] = useState("day");
  const [mode, setMode] = useState("regular");
  // Set once the user edits the name, so later previews stop overwriting it.
  const [nameTouched, setNameTouched] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const others = useMemo(
    () =>
      qualifications
        .filter((q) => q.id !== qualificationId)
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name)),
    [qualifications, qualificationId],
  );

  useEffect(() => {
    if (otherId === "") {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setLoadingPreview(true);
    setError(null);
    void (async () => {
      try {
        const data = await api.qualificationMergePreview(sessionId, qualificationId, otherId);
        if (cancelled) return;
        setPreview(data);
        if (!nameTouched) setName(data.suggested_name);
        setNumGroups(data.suggested_num_groups);
        setPeriod(data.first.schedule_period);
        setMode(data.first.delivery_mode);
      } catch (err) {
        if (!cancelled) {
          setPreview(null);
          setError(err instanceof Error ? err.message : "Could not load");
        }
      } finally {
        if (!cancelled) setLoadingPreview(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // nameTouched deliberately absent: it must not re-run the preview.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, qualificationId, otherId]);

  const periodsDiffer =
    !!preview && preview.first.schedule_period !== preview.second.schedule_period;
  const modesDiffer =
    !!preview && preview.first.delivery_mode !== preview.second.delivery_mode;
  const canMerge = !!preview && preview.combined_class_count > 0 && name.trim().length > 0;

  async function submit() {
    if (otherId === "") return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.mergeQualifications(sessionId, {
        first_qualification_id: qualificationId,
        second_qualification_id: otherId,
        name: name.trim(),
        num_groups: numGroups,
        schedule_period: period,
        delivery_mode: mode,
      });
      onMerge(result.summary, result.qualification_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Merge qualifications">
      <div className="modal-card qual-merge-card">
        <h2 className="qual-merge-title">Merge qualifications</h2>

        <label className="qual-merge-field">
          <span>Merge with</span>
          <select
            className="field-select"
            value={otherId}
            onChange={(e) => setOtherId(e.target.value === "" ? "" : Number(e.target.value))}
            disabled={busy}
          >
            <option value="">Choose a qualification…</option>
            {others.map((q) => (
              <option key={q.id} value={q.id}>
                {q.name}
              </option>
            ))}
          </select>
        </label>

        {others.length === 0 && (
          <p className="muted">
            There is only one qualification in this session, so there is nothing to merge with.
          </p>
        )}
        {loadingPreview && <p className="muted">Loading…</p>}

        {preview && (
          <>
            <div className="qual-merge-sides">
              {[preview.first, preview.second].map((side) => (
                <div key={side.id} className="qual-merge-side">
                  <div className="qual-merge-side-name">{side.name}</div>
                  <div className="qual-merge-side-meta muted">
                    {side.class_count} class(es) · {side.num_groups} group(s) ·{" "}
                    {side.schedule_period}
                    {side.booking_count > 0 && <> · {side.booking_count} booking(s)</>}
                  </div>
                </div>
              ))}
            </div>

            <p className="qual-merge-outcome">
              The new qualification will hold{" "}
              <strong>{preview.combined_class_count} class(es)</strong>
              {preview.shared_class_count > 0 && (
                <> ({preview.shared_class_count} of them in both, counted once)</>
              )}
              . <strong>{preview.first.name}</strong> and{" "}
              <strong>{preview.second.name}</strong> stay exactly as they are — their
              groups, bookings and classes are not touched.
            </p>

            {preview.warnings.map((w) => (
              <p key={w} className="qual-merge-warning">
                {w}
              </p>
            ))}

            <label className="qual-merge-field">
              <span>New qualification name</span>
              <input
                className="field-input"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setNameTouched(true);
                }}
                disabled={busy}
                required
              />
            </label>

            <label className="qual-merge-field">
              <span>Number of groups</span>
              <input
                className="field-input"
                type="number"
                min={1}
                max={26}
                value={numGroups}
                onChange={(e) => setNumGroups(Math.max(1, Number(e.target.value) || 1))}
                disabled={busy}
              />
            </label>

            {periodsDiffer && (
              <label className="qual-merge-field">
                <span>Schedule period</span>
                <select
                  className="field-select"
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                  disabled={busy}
                >
                  <option value="day">Day (08:30–19:00)</option>
                  <option value="night">Night (17:30–21:30)</option>
                </select>
              </label>
            )}

            {modesDiffer && (
              <label className="qual-merge-field">
                <span>Delivery mode</span>
                <select
                  className="field-select"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  disabled={busy}
                >
                  <option value="regular">Regular (weekly)</option>
                  <option value="block">Block (intensive)</option>
                </select>
              </label>
            )}

            {preview.combined_classes.length > 0 && (
              <fieldset className="qual-merge-classes">
                <legend>Classes in the merged qualification</legend>
                <ul className="entity-linked-list">
                  {preview.combined_classes.map((c) => (
                    <li key={c.id}>{c.name}</li>
                  ))}
                </ul>
              </fieldset>
            )}
          </>
        )}

        {error && <p className="error">{error}</p>}

        <div className="row gap qual-merge-actions">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !canMerge}
            onClick={() => void submit()}
          >
            {busy ? "Merging…" : "Create merged qualification"}
          </button>
          <button type="button" className="btn-secondary" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

/** Fold several duplicate classes into one linked to every qualification.
 *
 * The opposite of QualificationMergeDialog in temperament. That one only ever
 * adds a record, so it can be quiet. This one deletes rows: the classes being
 * folded in are gone afterwards, and anything hanging off them that is not
 * carried across goes with them. So the dialog spends most of its space on two
 * questions — which class survives, and what is about to be lost — and only
 * then offers the button.
 *
 * Called "consolidate" rather than "merge" throughout: "merge" already means
 * joining two clashing bookings in the staff view, and the two do entirely
 * different things.
 */
import { useEffect, useState } from "react";
import { api, Unit } from "../api";
import type { ClassConsolidationPreview } from "../types";

type Props = {
  sessionId: number;
  /** The ticked classes, in list order. At least two. */
  units: Unit[];
  onClose: () => void;
  onConsolidated: (summary: string, survivorId: number) => void;
};

export function ClassConsolidationDialog({
  sessionId,
  units,
  onClose,
  onConsolidated,
}: Props) {
  // The longest name is usually the most descriptive ("ICTNWK540 Manage
  // network security" over "ICTNWK540"), which is the better default to keep.
  const [survivorId, setSurvivorId] = useState<number>(() => {
    const best = units.reduce((a, b) => (b.name.length > a.name.length ? b : a), units[0]);
    return best?.id ?? 0;
  });
  const [preview, setPreview] = useState<ClassConsolidationPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // On by default: a surviving class that no longer records the units it
  // delivers is a quiet loss that only shows up later in the admin export.
  const [mergeCodes, setMergeCodes] = useState(true);

  const absorbedIds = units.map((u) => u.id).filter((id) => id !== survivorId);

  useEffect(() => {
    if (!survivorId || absorbedIds.length === 0) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setLoadingPreview(true);
    setError(null);
    void (async () => {
      try {
        const data = await api.classConsolidationPreview(sessionId, survivorId, absorbedIds);
        if (!cancelled) setPreview(data);
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
    // absorbedIds is derived from the two below; listing it would re-run on
    // every render because the array identity changes each time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, survivorId, units]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.consolidateClasses(sessionId, {
        survivor_id: survivorId,
        absorbed_ids: absorbedIds,
        merge_codes: mergeCodes,
      });
      onConsolidated(result.summary, result.survivor_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Consolidation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Consolidate classes"
    >
      <div className="modal-card class-merge-card">
        <h2 className="qual-merge-title">Consolidate classes</h2>

        <p className="muted">
          One class survives and picks up every qualification and group the others were
          linked to. Their placecards move onto it. The rest are deleted.
        </p>

        <fieldset className="class-merge-choice">
          <legend>Class to keep</legend>
          {units.map((u) => (
            <label key={u.id} className="class-merge-option">
              <input
                type="radio"
                name="survivor"
                checked={survivorId === u.id}
                onChange={() => setSurvivorId(u.id)}
                disabled={busy}
              />
              <span className="class-merge-option-name">{u.name}</span>
              {u.component_codes && (
                <span className="class-merge-option-codes muted">{u.component_codes}</span>
              )}
            </label>
          ))}
        </fieldset>

        {loadingPreview && <p className="muted">Loading…</p>}

        {preview && (
          <>
            <p className="qual-merge-outcome">
              <strong>{preview.survivor.name}</strong> will gain{" "}
              <strong>{preview.qualifications_gained} qualification(s)</strong> and{" "}
              <strong>{preview.groups_gained} group(s)</strong>, and{" "}
              <strong>{preview.bookings_moving} placecard(s)</strong> will move onto it.
              The other {preview.absorbed.length} class(es) are deleted.
            </p>

            {preview.combined_qualifications.length > 0 && (
              <fieldset className="qual-merge-classes">
                <legend>Qualifications it will be linked to</legend>
                <ul className="entity-linked-list">
                  {preview.combined_qualifications.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </fieldset>
            )}

            <fieldset className="qual-merge-classes">
              <legend>Classes being folded in</legend>
              <ul className="entity-linked-list">
                {preview.absorbed.map((a) => (
                  <li key={a.id}>
                    {a.name}
                    <span className="muted">
                      {" — "}
                      {a.qualifications.length || 0} qualification(s),{" "}
                      {a.booking_count} placecard(s)
                    </span>
                  </li>
                ))}
              </ul>
            </fieldset>

            <label className="class-merge-toggle">
              <input
                type="checkbox"
                checked={mergeCodes}
                onChange={(e) => setMergeCodes(e.target.checked)}
                disabled={busy}
              />
              <span>
                Carry the unit codes of the folded classes over to{" "}
                {preview.survivor.name}. Leave this on unless the surviving class
                genuinely does not deliver them.
              </span>
            </label>

            {preview.warnings.map((w) => (
              <p key={w} className="qual-merge-warning">
                {w}
              </p>
            ))}
          </>
        )}

        {error && <p className="error">{error}</p>}

        <div className="row gap qual-merge-actions">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !preview}
            onClick={() => void submit()}
          >
            {busy ? "Consolidating…" : `Consolidate ${units.length} classes`}
          </button>
          <button type="button" className="btn-secondary" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

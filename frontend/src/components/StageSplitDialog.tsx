/** Deal one qualification's classes out into a stage each.
 *
 * Each stage becomes its own qualification with its own groups, matching how
 * staged qualifications are already written by hand ("… Stg1", "… Stg2"). The
 * dialog therefore asks for the two things a qualification needs — a name and
 * a group count — plus which classes belong to it.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { StageSplitPreview } from "../types";

type Props = {
  sessionId: number;
  qualificationId: number;
  onClose: () => void;
  onSplit: (summary: string) => void;
};

type StageDraft = { name: string; numGroups: number; unitIds: Set<number> };

const MAX_STAGES = 8;

function defaultStages(baseName: string, count: number, groups: number): StageDraft[] {
  // Strip any stage suffix the name already carries, so splitting
  // "Cert IV Cyber Stg1" doesn't produce "Cert IV Cyber Stg1 Stg1".
  const stem = baseName.replace(/\s*St(?:a?ge?)?\s*\d+\s*$/i, "").trim() || baseName;
  return Array.from({ length: count }, (_, i) => ({
    name: `${stem} Stg${i + 1}`,
    numGroups: groups,
    unitIds: new Set<number>(),
  }));
}

export function StageSplitDialog({ sessionId, qualificationId, onClose, onSplit }: Props) {
  const [preview, setPreview] = useState<StageSplitPreview | null>(null);
  const [stages, setStages] = useState<StageDraft[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await api.stageSplitPreview(sessionId, qualificationId);
        if (cancelled) return;
        setPreview(data);
        setStages(defaultStages(data.name, 2, data.num_groups || 1));
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, qualificationId]);

  /** Which stage a class currently sits in, so a class can't be in two. */
  const stageOfUnit = useMemo(() => {
    const map = new Map<number, number>();
    stages.forEach((s, i) => s.unitIds.forEach((id) => map.set(id, i)));
    return map;
  }, [stages]);

  function setStageCount(count: number) {
    setStages((prev) => {
      const next = defaultStages(preview?.name ?? "", count, preview?.num_groups || 1);
      // Keep what has already been assigned where the stage still exists.
      for (let i = 0; i < Math.min(prev.length, count); i++) {
        next[i] = { ...next[i], name: prev[i].name, numGroups: prev[i].numGroups, unitIds: prev[i].unitIds };
      }
      return next;
    });
  }

  function assign(unitId: number, stageIndex: number | null) {
    setStages((prev) =>
      prev.map((s, i) => {
        const ids = new Set(s.unitIds);
        ids.delete(unitId);
        if (i === stageIndex) ids.add(unitId);
        return { ...s, unitIds: ids };
      }),
    );
  }

  const unassigned = (preview?.classes ?? []).filter((c) => !stageOfUnit.has(c.id));

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.stageSplit(sessionId, qualificationId, {
        stages: stages.map((s) => ({
          name: s.name.trim(),
          num_groups: s.numGroups,
          unit_ids: [...s.unitIds],
        })),
      });
      onSplit(result.summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Split failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Stage split">
      <div className="modal-card stage-split-card">
        <h2 className="stage-split-title">Stage split{preview ? ` — ${preview.name}` : ""}</h2>

        {!preview && !error && <p className="muted">Loading…</p>}
        {error && <p className="error">{error}</p>}

        {preview && !preview.can_split && (
          <p className="error stage-split-blocked">{preview.blocked_reason}</p>
        )}

        {preview && preview.can_split && (
          <>
            <label className="stage-split-count">
              <span>Number of stages</span>
              <select
                className="field-select"
                value={stages.length}
                onChange={(e) => setStageCount(Number(e.target.value))}
                disabled={busy}
              >
                {Array.from({ length: MAX_STAGES - 1 }, (_, i) => i + 2).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>

            <div className="stage-split-grid">
              {stages.map((stage, i) => (
                <section key={i} className="stage-split-col">
                  <input
                    className="stage-split-name"
                    value={stage.name}
                    disabled={busy}
                    aria-label={`Stage ${i + 1} name`}
                    onChange={(e) =>
                      setStages((prev) =>
                        prev.map((s, j) => (j === i ? { ...s, name: e.target.value } : s)),
                      )
                    }
                  />
                  <label className="stage-split-groups">
                    <span>Groups</span>
                    <input
                      type="number"
                      min={1}
                      max={26}
                      value={stage.numGroups}
                      disabled={busy}
                      onChange={(e) =>
                        setStages((prev) =>
                          prev.map((s, j) =>
                            j === i ? { ...s, numGroups: Math.max(1, Number(e.target.value) || 1) } : s,
                          ),
                        )
                      }
                    />
                  </label>
                  <ul className="stage-split-classes">
                    {(preview.classes ?? [])
                      .filter((c) => stageOfUnit.get(c.id) === i)
                      .map((c) => (
                        <li key={c.id}>
                          <button
                            type="button"
                            className="stage-split-chip"
                            disabled={busy}
                            title="Remove from this stage"
                            onClick={() => assign(c.id, null)}
                          >
                            {c.name} ✕
                          </button>
                        </li>
                      ))}
                    {!stages[i].unitIds.size && <li className="muted stage-split-empty">No classes yet</li>}
                  </ul>
                </section>
              ))}
            </div>

            <div className="stage-split-pool">
              <h3 className="stage-split-pool-title">
                Unassigned classes
                <span className="muted"> — click a stage to place each one</span>
              </h3>
              {!unassigned.length && <p className="muted">All classes assigned.</p>}
              <ul className="stage-split-pool-list">
                {unassigned.map((c) => (
                  <li key={c.id} className="stage-split-pool-row">
                    <span className="stage-split-pool-name">{c.name}</span>
                    {stages.map((s, i) => (
                      <button
                        key={i}
                        type="button"
                        className="btn-secondary btn-xs"
                        disabled={busy}
                        onClick={() => assign(c.id, i)}
                      >
                        {s.name.trim() || `Stage ${i + 1}`}
                      </button>
                    ))}
                  </li>
                ))}
              </ul>
              {!!unassigned.length && (
                <p className="muted stage-split-note">
                  Anything left here stays with the first stage.
                </p>
              )}
            </div>
          </>
        )}

        <div className="row gap stage-split-actions">
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !preview?.can_split}
            onClick={() => void submit()}
          >
            {busy ? "Splitting…" : "Split into stages"}
          </button>
          <button type="button" className="btn-secondary" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

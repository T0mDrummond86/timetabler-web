/** Deal one qualification's classes out into a stage each.
 *
 * Each stage becomes its own qualification with its own groups, matching how
 * staged qualifications are already written by hand ("… Stg1", "… Stg2"). The
 * dialog therefore asks for the two things a qualification needs — a name and
 * a group count — plus which classes belong to it.
 *
 * Assignment is one row per class with a stage dropdown, rather than a button
 * per stage on every row: the row count then depends only on how many classes
 * there are, so six stages read exactly as calmly as two.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { stripStageSuffix } from "../stageFamily";
import type { StageSplitPreview } from "../types";

type Props = {
  sessionId: number;
  qualificationId: number;
  onClose: () => void;
  onSplit: (summary: string) => void;
};

type StageDraft = { name: string; numGroups: number; unitIds: Set<number> };

const MAX_STAGES = 6;

function defaultStages(baseName: string, count: number, groups: number): StageDraft[] {
  // Strip any stage suffix the name already carries, so splitting
  // "Cert IV Cyber Stg1" doesn't produce "Cert IV Cyber Stg1 Stg1".
  const stem = stripStageSuffix(baseName);
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
        next[i] = {
          ...next[i],
          name: prev[i].name,
          numGroups: prev[i].numGroups,
          unitIds: prev[i].unitIds,
        };
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

  function editStage(index: number, patch: Partial<StageDraft>) {
    setStages((prev) => prev.map((s, j) => (j === index ? { ...s, ...patch } : s)));
  }

  const classes = preview?.classes ?? [];
  const unassignedCount = classes.filter((c) => !stageOfUnit.has(c.id)).length;

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

            <table className="stage-split-table stage-split-stages">
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Name</th>
                  <th className="stage-split-num">Groups</th>
                  <th className="stage-split-num">Classes</th>
                </tr>
              </thead>
              <tbody>
                {stages.map((stage, i) => (
                  <tr key={i}>
                    <td className="stage-split-index">{i + 1}</td>
                    <td>
                      <input
                        className="stage-split-name"
                        value={stage.name}
                        disabled={busy}
                        aria-label={`Stage ${i + 1} name`}
                        onChange={(e) => editStage(i, { name: e.target.value })}
                      />
                    </td>
                    <td className="stage-split-num">
                      <input
                        type="number"
                        className="stage-split-groups-input"
                        min={1}
                        max={26}
                        value={stage.numGroups}
                        disabled={busy}
                        aria-label={`Stage ${i + 1} groups`}
                        onChange={(e) =>
                          editStage(i, { numGroups: Math.max(1, Number(e.target.value) || 1) })
                        }
                      />
                    </td>
                    <td className="stage-split-num muted">{stage.unitIds.size}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="stage-split-pool">
              <h3 className="stage-split-pool-title">
                Classes
                <span className="muted"> — choose the stage each one belongs to</span>
              </h3>
              <table className="stage-split-table stage-split-classes-table">
                <tbody>
                  {classes.map((c) => {
                    const at = stageOfUnit.get(c.id);
                    return (
                      <tr key={c.id} className={at == null ? "stage-split-row--unassigned" : ""}>
                        <td className="stage-split-class-name">{c.name}</td>
                        <td className="stage-split-num">
                          <select
                            className="field-select stage-split-pick"
                            value={at ?? ""}
                            disabled={busy}
                            aria-label={`Stage for ${c.name}`}
                            onChange={(e) =>
                              assign(c.id, e.target.value === "" ? null : Number(e.target.value))
                            }
                          >
                            <option value="">Unassigned</option>
                            {stages.map((_, i) => (
                              // Numbers, not names: the stage names run to 70-odd
                              // characters here and truncate to nothing useful.
                              // The table above is the number-to-name key.
                              <option key={i} value={i}>
                                Stage {i + 1}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {!!unassignedCount && (
                <p className="muted stage-split-note">
                  {unassignedCount} class(es) still unassigned — anything left that way stays with
                  the first stage.
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

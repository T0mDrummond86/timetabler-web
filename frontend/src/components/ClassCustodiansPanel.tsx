import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { ClassCustodians } from "../types";
import { ClassCustodiansTable } from "./ClassCustodiansTable";

type Props = {
  sessionId: number;
  refreshKey?: number;
  /** Every lecturer in the session, so a custodian need not deliver the class. */
  staff?: { id: number; name: string }[];
  /** False for read-only access — the picker becomes plain text. */
  canEdit?: boolean;
};

export function ClassCustodiansPanel({
  sessionId,
  refreshKey = 0,
  staff = [],
  canEdit = true,
}: Props) {
  const [data, setData] = useState<ClassCustodians | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.classCustodians(sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load class custodians");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const reassign = useCallback(
    async (unitId: number, staffId: number | null) => {
      setSaving(true);
      setError(null);
      try {
        // The endpoint returns the whole recomputed report, so the summary and
        // every derived custodian stay in step with the change.
        setData(await api.setUnitCustodian(sessionId, unitId, staffId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not change the custodian");
      } finally {
        setSaving(false);
      }
    },
    [sessionId],
  );

  const tableRows =
    data?.rows.map((row) => ({
      unit_id: row.unit_id,
      unit_name: row.unit_name,
      qualifications: row.qualifications ?? "—",
      lecturers: row.lecturers,
      custodian: row.custodian,
      custodian_staff_id: row.custodian_staff_id,
      custodian_deliveries: row.custodian_deliveries,
      custodian_is_manual: row.custodian_is_manual,
      candidates: row.candidates,
    })) ?? [];

  return (
    <section className="panel class-custodians-panel">
      <div className="panel-header">
        <h2>Class custodians</h2>
        <button type="button" className="btn-secondary" onClick={() => void load()} disabled={loading}>
          Refresh
        </button>
      </div>
      <div className="panel-body">
        {error && <p className="error">{error}</p>}
        {loading && !data && <p className="muted">Loading…</p>}
        {data && (
          <ClassCustodiansTable
            rows={tableRows}
            summary={data.summary}
            allStaff={staff}
            saving={saving}
            onReassign={canEdit ? (unitId, staffId) => void reassign(unitId, staffId) : undefined}
          />
        )}
      </div>
    </section>
  );
}

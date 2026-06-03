import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { ClassCustodians } from "../types";
import { ClassCustodiansTable } from "./ClassCustodiansTable";

type Props = {
  sessionId: number;
  refreshKey?: number;
};

export function ClassCustodiansPanel({ sessionId, refreshKey = 0 }: Props) {
  const [data, setData] = useState<ClassCustodians | null>(null);
  const [loading, setLoading] = useState(true);
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

  const tableRows =
    data?.rows.map((row) => ({
      unit_id: row.unit_id,
      unit_name: row.unit_name,
      qualifications: row.qualifications ?? "—",
      lecturers: row.lecturers,
      custodian: row.custodian,
      custodian_deliveries: row.custodian_deliveries,
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
          <ClassCustodiansTable rows={tableRows} summary={data.summary} />
        )}
      </div>
    </section>
  );
}

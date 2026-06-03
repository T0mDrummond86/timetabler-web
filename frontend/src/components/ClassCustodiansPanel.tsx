import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { ClassCustodians } from "../types";

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
          <>
            <p className="violations-summary">{data.summary}</p>
            {!data.rows.length ? (
              <p className="muted">No classes in this session.</p>
            ) : (
              <div className="violations-table-scroll">
                <table className="violations-table class-custodians-table">
                  <thead>
                    <tr>
                      <th>Class</th>
                      <th>Lecturers (deliveries)</th>
                      <th>Custodian</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row) => (
                      <tr key={row.unit_id}>
                        <td>{row.unit_name}</td>
                        <td>{row.lecturers}</td>
                        <td>
                          {row.custodian}
                          {row.custodian !== "—" && (
                            <span className="muted"> ({row.custodian_deliveries})</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

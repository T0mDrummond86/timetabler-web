import { useMemo, useState } from "react";

export type ClassCustodianTableRow = {
  unit_id: number;
  unit_name: string;
  qualifications: string;
  lecturers: string;
  custodian: string;
  custodian_deliveries?: number;
  session_name?: string;
  session_names?: string[];
};

type Props = {
  rows: ClassCustodianTableRow[];
  summary?: string;
  emptyMessage?: string;
  /** @deprecated use amalgamatedSessions */
  showSessionColumn?: boolean;
  /** Global view: one row per class with session_names list */
  amalgamatedSessions?: boolean;
};

const ALL = "";

function parseStaffNames(lecturers: string, custodian: string): string[] {
  const names = new Set<string>();
  const addFromSegment = (segment: string) => {
    const body = segment.includes(":") ? segment.split(":").slice(1).join(":") : segment;
    for (const part of body.split(",")) {
      const trimmed = part.trim();
      if (!trimmed || /^unassigned\b/i.test(trimmed)) continue;
      const m = trimmed.match(/^(.+?)\s+\(\d+\)\s*$/);
      names.add((m ? m[1] : trimmed).trim());
    }
  };

  if (custodian && custodian !== "—") {
    if (custodian.includes(":")) {
      addFromSegment(custodian);
    } else {
      names.add(custodian.trim());
    }
  }
  for (const segment of lecturers.split(";")) {
    addFromSegment(segment);
  }
  return [...names];
}

function parseQualificationNames(qualifications: string): string[] {
  const raw = (qualifications || "").trim();
  if (!raw || raw === "—") return [];
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

function rowSessionNames(row: ClassCustodianTableRow): string[] {
  if (row.session_names?.length) return row.session_names;
  if (row.session_name) return [row.session_name];
  return [];
}

function rowMatchesStaff(row: ClassCustodianTableRow, staffName: string): boolean {
  return parseStaffNames(row.lecturers, row.custodian).some(
    (n) => n.toLowerCase() === staffName.toLowerCase(),
  );
}

function rowMatchesQual(row: ClassCustodianTableRow, qualName: string): boolean {
  return parseQualificationNames(row.qualifications).some(
    (q) => q.toLowerCase() === qualName.toLowerCase(),
  );
}

export function ClassCustodiansTable({
  rows,
  summary,
  emptyMessage = "No classes match the current filters.",
  showSessionColumn = false,
  amalgamatedSessions = false,
}: Props) {
  const [sessionFilter, setSessionFilter] = useState(ALL);
  const [classFilter, setClassFilter] = useState(ALL);
  const [staffFilter, setStaffFilter] = useState(ALL);
  const [qualFilter, setQualFilter] = useState(ALL);

  const hasSession = amalgamatedSessions || showSessionColumn || rows.some((r) => rowSessionNames(r).length > 0);

  const sessionOptions = useMemo(() => {
    const names = new Set<string>();
    for (const row of rows) {
      for (const sn of rowSessionNames(row)) names.add(sn);
    }
    return [...names].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }, [rows]);

  const classOptions = useMemo(() => {
    const names = new Set(rows.map((r) => r.unit_name));
    return [...names].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }, [rows]);

  const staffOptions = useMemo(() => {
    const names = new Set<string>();
    for (const row of rows) {
      for (const n of parseStaffNames(row.lecturers, row.custodian)) names.add(n);
    }
    return [...names].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }, [rows]);

  const qualOptions = useMemo(() => {
    const names = new Set<string>();
    for (const row of rows) {
      for (const q of parseQualificationNames(row.qualifications)) names.add(q);
    }
    return [...names].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }, [rows]);

  const filtered = useMemo(() => {
    return rows.filter((row) => {
      if (sessionFilter && !rowSessionNames(row).includes(sessionFilter)) return false;
      if (classFilter && row.unit_name !== classFilter) return false;
      if (staffFilter && !rowMatchesStaff(row, staffFilter)) return false;
      if (qualFilter && !rowMatchesQual(row, qualFilter)) return false;
      return true;
    });
  }, [rows, sessionFilter, classFilter, staffFilter, qualFilter]);

  const filtersActive = Boolean(sessionFilter || classFilter || staffFilter || qualFilter);

  const filterSummary =
    filtersActive && rows.length > 0
      ? `Showing ${filtered.length} of ${rows.length} row(s)`
      : null;

  const sessionColumnLabel = amalgamatedSessions ? "Used in sessions" : "Session";

  function clearFilters() {
    setSessionFilter(ALL);
    setClassFilter(ALL);
    setStaffFilter(ALL);
    setQualFilter(ALL);
  }

  return (
    <>
      {summary && <p className="violations-summary">{summary}</p>}
      {filterSummary && <p className="muted entity-hint">{filterSummary}</p>}
      <div className="entity-list-filters class-custodians-filters">
        {hasSession && (
          <label>
            Session
            <select
              className="field-select"
              value={sessionFilter}
              onChange={(e) => setSessionFilter(e.target.value)}
            >
              <option value={ALL}>All sessions</option>
              {sessionOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Class
          <select
            className="field-select"
            value={classFilter}
            onChange={(e) => setClassFilter(e.target.value)}
          >
            <option value={ALL}>All classes</option>
            {classOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Staff
          <select
            className="field-select"
            value={staffFilter}
            onChange={(e) => setStaffFilter(e.target.value)}
          >
            <option value={ALL}>All staff</option>
            {staffOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Qualification
          <select
            className="field-select"
            value={qualFilter}
            onChange={(e) => setQualFilter(e.target.value)}
          >
            <option value={ALL}>All qualifications</option>
            {qualOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {filtersActive && (
          <button
            type="button"
            className="btn-secondary btn-xs class-custodians-clear-filters"
            onClick={clearFilters}
          >
            Clear filters
          </button>
        )}
      </div>
      {!rows.length ? (
        <p className="muted">No classes in this session.</p>
      ) : !filtered.length ? (
        <p className="muted">{emptyMessage}</p>
      ) : (
        <div className="violations-table-scroll">
          <table className="violations-table class-custodians-table">
            <thead>
              <tr>
                {hasSession && <th>{sessionColumnLabel}</th>}
                <th>Class</th>
                <th>Linked qualifications</th>
                <th>Lecturers (deliveries)</th>
                <th>Custodian</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr
                  key={
                    amalgamatedSessions
                      ? row.unit_name
                      : `${rowSessionNames(row).join("-")}-${row.unit_id}`
                  }
                >
                  {hasSession && <td>{rowSessionNames(row).join(", ") || "—"}</td>}
                  <td>{row.unit_name}</td>
                  <td>{row.qualifications || "—"}</td>
                  <td>{row.lecturers}</td>
                  <td>
                    {row.custodian}
                    {row.custodian !== "—" &&
                      row.custodian_deliveries != null &&
                      row.custodian_deliveries > 0 && (
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
  );
}

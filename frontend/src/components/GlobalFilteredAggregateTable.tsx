import { useMemo, useState, type ReactNode } from "react";
import { formatHours } from "../lib/staffVariance";

const ALL = "";

export type GlobalFilterDef<TRow> = {
  id: string;
  label: string;
  options: (rows: TRow[]) => { value: string; label: string }[];
  match: (row: TRow, value: string) => boolean;
};

export type GlobalColumnDef<TRow> = {
  header: string;
  cell: (row: TRow) => string | number;
  cellClassName?: (row: TRow) => string | undefined;
};

type Props<TRow> = {
  rows: TRow[];
  columns: GlobalColumnDef<TRow>[];
  filters: GlobalFilterDef<TRow>[];
  empty: string;
};

export function sessionFilter<TRow extends { session_names: string[] }>(): GlobalFilterDef<TRow> {
  return {
    id: "session",
    label: "Used in sessions",
    options: (rows) => {
      const names = new Set<string>();
      for (const r of rows) {
        for (const s of r.session_names) names.add(s);
      }
      return [...names]
        .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }))
        .map((n) => ({ value: n, label: n }));
    },
    match: (row, value) => row.session_names.includes(value),
  };
}

export function uniqFieldFilter<TRow>(
  id: string,
  label: string,
  getValue: (row: TRow) => string | number | null | undefined,
  formatLabel?: (value: string) => string,
): GlobalFilterDef<TRow> {
  return {
    id,
    label,
    options: (rows) => {
      const vals = new Set<string>();
      for (const r of rows) {
        const v = getValue(r);
        if (v === "Varies") vals.add("Varies");
        else if (v == null || v === "") vals.add("—");
        else vals.add(String(v));
      }
      return [...vals]
        .sort((a, b) => {
          if (a === "—") return 1;
          if (b === "—") return -1;
          if (a === "Varies") return 1;
          if (b === "Varies") return -1;
          return a.localeCompare(b, undefined, { sensitivity: "base" });
        })
        .map((value) => ({
          value,
          label: formatLabel ? formatLabel(value) : value,
        }));
    },
    match: (row, value) => {
      const raw = getValue(row);
      if (value === "—") return raw == null || raw === "" || raw === "—";
      if (value === "Varies") return raw === "Varies";
      return String(raw ?? "") === value;
    },
  };
}

export function qualificationListFilter<TRow>(
  getQualifications: (row: TRow) => string,
): GlobalFilterDef<TRow> {
  return {
    id: "qualification",
    label: "Linked qualification",
    options: (rows) => {
      const names = new Set<string>();
      for (const r of rows) {
        const raw = (getQualifications(r) || "").trim();
        if (!raw || raw === "—") continue;
        for (const q of raw.split(",")) {
          const t = q.trim();
          if (t) names.add(t);
        }
      }
      return [...names]
        .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }))
        .map((n) => ({ value: n, label: n }));
    },
    match: (row, value) => {
      const raw = (getQualifications(row) || "").trim();
      if (!raw || raw === "—") return false;
      return raw.split(",").some((q) => q.trim().toLowerCase() === value.toLowerCase());
    },
  };
}

const VARIANCE_TOLERANCE = 0.001;

export function varianceSignFilter<TRow extends { member_variances?: (number | null)[] }>(): GlobalFilterDef<TRow> {
  return {
    id: "variance",
    label: "Variance",
    options: () => [
      { value: "under", label: "Under 0 (shortfall)" },
      { value: "over", label: "Over 0 (overtime)" },
    ],
    match: (row, value) => {
      const vals = (row.member_variances ?? []).filter(
        (v): v is number => v != null && !Number.isNaN(v),
      );
      if (!vals.length) return false;
      if (value === "under") return vals.some((v) => v < -VARIANCE_TOLERANCE);
      if (value === "over") return vals.some((v) => v > VARIANCE_TOLERANCE);
      return true;
    },
  };
}

export function formatGlobalVariance(
  variance: number | string | null | undefined,
): string {
  if (variance === "Varies") return "Varies";
  if (variance == null || variance === "") return "—";
  if (typeof variance === "number") return formatHours(variance);
  return String(variance);
}

export function GlobalFilteredAggregateTable<TRow>({
  rows,
  columns,
  filters,
  empty,
}: Props<TRow>) {
  const [filterValues, setFilterValues] = useState<Record<string, string>>({});

  const filterOptions = useMemo(() => {
    const out: Record<string, { value: string; label: string }[]> = {};
    for (const f of filters) {
      out[f.id] = f.options(rows);
    }
    return out;
  }, [rows, filters]);

  const filtered = useMemo(() => {
    return rows.filter((row) =>
      filters.every((f) => {
        const val = filterValues[f.id] ?? ALL;
        if (!val) return true;
        return f.match(row, val);
      }),
    );
  }, [rows, filters, filterValues]);

  const filtersActive = Object.values(filterValues).some((v) => v !== "");

  return (
    <section className="card global-aggregate-table-wrap">
      {filters.length > 0 && (
        <>
          <div className="entity-list-filters class-custodians-filters global-aggregate-filters">
            {filters.map((f) => (
              <label key={f.id}>
                {f.label}
                <select
                  className="field-select"
                  value={filterValues[f.id] ?? ALL}
                  onChange={(e) =>
                    setFilterValues((prev) => ({ ...prev, [f.id]: e.target.value }))
                  }
                >
                  <option value={ALL}>All</option>
                  {filterOptions[f.id]?.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            {filtersActive && (
              <button
                type="button"
                className="btn-secondary btn-xs class-custodians-clear-filters"
                onClick={() => setFilterValues({})}
              >
                Clear filters
              </button>
            )}
          </div>
          {filtersActive && rows.length > 0 && (
            <p className="muted entity-hint global-aggregate-filter-summary">
              Showing {filtered.length} of {rows.length} row(s)
            </p>
          )}
        </>
      )}
      <div className="global-aggregate-table-scroll">
        <table className="global-aggregate-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.header}>{col.header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((row, i) => (
              <tr key={i}>
                {columns.map((col) => {
                  const cls = col.cellClassName?.(row);
                  const content: ReactNode = col.cell(row);
                  return (
                    <td key={col.header} className={cls}>
                      {content}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!filtered.length && (
              <tr>
                <td colSpan={columns.length} className="muted empty-cell">
                  {rows.length ? "No rows match the current filters." : empty}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

import { useMemo, useState, type MouseEvent } from "react";
import type { StaffHoursRow } from "../types";
import {
  formatHours,
  formatFte,
  formatOptionalNum,
  VARIANCE_FILTER_OPTIONS,
  varianceTooltip,
  type StaffVarianceCategory,
} from "../lib/staffVariance";
import { LoadingMark } from "./LoadingMark";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

type Props = {
  rows: StaffHoursRow[];
  selectedId: number | null;
  onSelect: (staffId: number) => void;
  loading?: boolean;
};

type VarianceTone = "positive" | "negative" | "neutral" | "unknown";

function staffInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

/** Colour follows the sign of the number on the badge.
 *
 * The category alone cannot decide it: for a part-time lecturer the backend
 * sorts on total hours against a *full-time* 21, so someone on 0.5 FTE
 * carrying 12 hours is "part_fte_variation" — the same category as one
 * carrying 8 — even though the first is over their own load and the second
 * under it. Reading the sign keeps "+1.5" from being painted as a shortfall.
 */
function varianceTone(category: string, value: number | null | undefined): VarianceTone {
  if (category === "unknown" || !category) return "unknown";
  if (value == null || Number.isNaN(value)) {
    return category === "on_target" ? "neutral" : "unknown";
  }
  if (Math.abs(value) < 0.05) return "neutral";
  return value > 0 ? "positive" : "negative";
}

function formatVarianceDisplay(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const fixed = Math.abs(v).toFixed(1);
  if (Math.abs(v) < 0.05) return "0.0";
  if (v > 0) return `+${fixed}`;
  return `−${fixed}`;
}

/** Current FTE = total workload ÷ 21, capped at 1.0. */
function formatCurrentFte(total: number | null | undefined): string {
  if (total == null || Number.isNaN(total)) return "—";
  return Math.min(1, total / 21).toFixed(2);
}

/** Lecturing hours, rounded to the nearest 0.5. */
function formatLecturingHours(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return (Math.round(v * 2) / 2).toFixed(1);
}

function parseBulkOnlineLines(detail: string | null): string[] {
  if (!detail || detail === "—") return [];
  return detail
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function bulkOnlineSummary(lines: string[]) {
  const items = lines.filter((line) => !/^Term \d+:$/.test(line));
  const first = items[0] ?? lines[0] ?? "";
  const extra = Math.max(0, items.length - 1);
  return { first, extra, all: lines };
}

function StaffSummaryCards({ rows }: { rows: StaffHoursRow[] }) {
  const stats = useMemo(() => {
    let overloaded = 0;
    let underloaded = 0;
    let balanced = 0;
    for (const row of rows) {
      switch (varianceTone(row.variance_category, row.variance)) {
        case "neutral":
          balanced += 1;
          break;
        case "positive":
          overloaded += 1;
          break;
        case "negative":
          underloaded += 1;
          break;
        default:
          break;
      }
    }
    return { total: rows.length, overloaded, underloaded, balanced };
  }, [rows]);

  return (
    <div className="staff-hours-summary-cards" aria-label="Workload summary">
      <div className="staff-hours-summary-card">
        <span className="staff-hours-summary-card__label">Total lecturers</span>
        <span className="staff-hours-summary-card__value">{stats.total}</span>
      </div>
      <div className="staff-hours-summary-card staff-hours-summary-card--positive">
        <span className="staff-hours-summary-card__label">Overloaded</span>
        <span className="staff-hours-summary-card__value">{stats.overloaded}</span>
      </div>
      <div className="staff-hours-summary-card staff-hours-summary-card--negative">
        <span className="staff-hours-summary-card__label">Underloaded</span>
        <span className="staff-hours-summary-card__value">{stats.underloaded}</span>
      </div>
      <div className="staff-hours-summary-card staff-hours-summary-card--neutral">
        <span className="staff-hours-summary-card__label">Balanced</span>
        <span className="staff-hours-summary-card__value">{stats.balanced}</span>
      </div>
    </div>
  );
}

function VarianceBadge({
  value,
  category,
}: {
  value: number | null;
  category: string;
}) {
  const tone = varianceTone(category, value);
  return (
    <span
      className={`variance-badge variance-badge--${tone}`}
      title={varianceTooltip(category)}
    >
      <span className={`variance-badge__dot variance-badge__dot--${tone}`} aria-hidden />
      <span className="variance-badge__value">{formatVarianceDisplay(value)}</span>
    </span>
  );
}

function BulkOnlineCell({
  detail,
  rowId,
  expanded,
  onToggle,
}: {
  detail: string | null;
  rowId: number;
  expanded: boolean;
  onToggle: (rowId: number, e: MouseEvent) => void;
}) {
  const lines = useMemo(() => parseBulkOnlineLines(detail), [detail]);
  if (!lines.length) {
    return <span className="staff-bulk-online-empty">—</span>;
  }

  const { first, extra, all } = bulkOnlineSummary(lines);

  if (expanded) {
    return (
      <div className="staff-bulk-online">
        <pre className="staff-bulk-online__full">{all.join("\n")}</pre>
        <button
          type="button"
          className="staff-bulk-online__toggle"
          onClick={(e) => onToggle(rowId, e)}
        >
          Show less
        </button>
      </div>
    );
  }

  return (
    <div className="staff-bulk-online">
      <span className="staff-bulk-online__summary">{first}</span>
      {extra > 0 && (
        <button
          type="button"
          className="staff-bulk-online__toggle"
          onClick={(e) => onToggle(rowId, e)}
        >
          +{extra} more allocation{extra === 1 ? "" : "s"}
        </button>
      )}
    </div>
  );
}

export function StaffHoursTable({ rows, selectedId, onSelect, loading }: Props) {
  const [search, setSearch] = useState("");
  const [varianceFilter, setVarianceFilter] = useState<"all" | StaffVarianceCategory>("all");
  const [expandedBulkIds, setExpandedBulkIds] = useState<Set<number>>(() => new Set());

  const searchFiltered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => {
      const hay = [
        r.name,
        r.cost_centre,
        r.preferences_first,
        r.preferences_second,
        r.preferences_third,
        r.development_project_description,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [rows, search]);

  const filtered = useMemo(() => {
    if (varianceFilter === "all") return searchFiltered;
    return searchFiltered.filter((r) => r.variance_category === varianceFilter);
  }, [searchFiltered, varianceFilter]);

  const toggleBulkExpanded = (rowId: number, e: MouseEvent) => {
    e.stopPropagation();
    setExpandedBulkIds((prev) => {
      const next = new Set(prev);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  };

  return (
    <div className={`staff-hours-table-wrap${loading && rows.length === 0 ? " staff-hours-table-wrap--loading" : ""}`}>
      {loading && rows.length === 0 ? (
        <LoadingMark label="Loading hours…" />
      ) : (
        <>
      <StaffSummaryCards rows={rows} />

      <div className="staff-hours-table-toolbar">
        <div className="staff-hours-table-filters">
          <input
            type="search"
            className="field-input staff-list-search"
            placeholder="Search lecturers…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search lecturers"
          />
          <label className="staff-variance-filter">
            <span>Variance filter</span>
            <select
              value={varianceFilter}
              onChange={(e) => setVarianceFilter(e.target.value as typeof varianceFilter)}
              title="Show only lecturers whose variance cell matches the selected category."
            >
              {VARIANCE_FILTER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {loading ? (
          <LoadingMark size={40} label="Loading hours…" className="loading-mark--inline staff-hours-loading-mark" />
        ) : (
          <span className="muted staff-hours-table-count">
            {filtered.length} of {rows.length} lecturer{rows.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      <div className="staff-hours-table-scroll">
        <table className="staff-hours-table">
          <thead>
            <tr>
              <th className="staff-col-primary staff-col-sticky">Lecturer</th>
              {/* Total and variance lead: they are what the table is read for. */}
              <th
                className="staff-col-metric staff-col-metric-highlight"
                title="In-class + bulk online + dev + PD + supervision"
              >
                Total
              </th>
              <th
                className="staff-col-metric staff-col-variance"
                title="Total workload minus lecturing hours"
              >
                Variance
              </th>
              <th
                className="staff-col-metric staff-col-owed"
                title="Weekly shortfall across the semester, for lecturers under their hours"
              >
                Hours owed
              </th>
              <th
                className="staff-col-metric staff-col-owed"
                title="What is still owed once logged cover jobs are credited"
              >
                Owed after cover
              </th>
              <th className="staff-col-meta">Cost centre</th>
              <th className="staff-col-metric staff-col-metric-group">Subst. FTE</th>
              <th
                className="staff-col-metric"
                title="Total workload ÷ 21, capped at 1.0"
              >
                Current FTE
              </th>
              <th
                className="staff-col-metric"
                title="Subst. FTE × 21 hours per FTE"
              >
                Lecturing h
              </th>
              <th
                className="staff-col-metric staff-col-metric-highlight"
                title="Weekly in-class scheduled contact (non-online rooms), session-adjusted"
              >
                In-class h
              </th>
              <th
                className="staff-col-meta"
                title="Sessions × hours ÷ 20 weeks when class runs fewer than all semester weeks"
              >
                Session avg
              </th>
              <th
                className="staff-col-detail staff-hours-bulk-online-col"
                title="Per-class online session detail"
              >
                Bulk online
              </th>
              <th className="staff-col-metric" title="Online / collaborate load hours">
                Bulk online h
              </th>
              <th className="staff-col-meta staff-col-meta-group">Dev &amp; project</th>
              <th className="staff-col-meta">Dev description</th>
              <th className="staff-col-meta">PD / training</th>
              <th className="staff-col-meta">Supervision</th>
              <th className="staff-col-meta">Non-teach day</th>
              <th className="staff-col-meta staff-col-meta-group">1st prefs</th>
              <th className="staff-col-meta">2nd prefs</th>
              <th className="staff-col-meta">3rd prefs</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr
                key={row.id}
                className={
                  selectedId === row.id
                    ? "staff-hours-row staff-hours-row--selected"
                    : "staff-hours-row"
                }
                onClick={() => onSelect(row.id)}
              >
                <td className="staff-col-primary staff-col-sticky">
                  <div className="staff-lecturer-cell">
                    <span className="staff-avatar" aria-hidden>
                      {staffInitials(row.name)}
                    </span>
                    <span className="staff-hours-name" title={row.name}>
                      {row.name}
                    </span>
                  </div>
                </td>
                <td className="staff-col-metric staff-col-metric-highlight">
                  {formatHours(row.total_hours)}
                </td>
                <td className="staff-col-metric staff-col-variance">
                  <VarianceBadge value={row.variance} category={row.variance_category} />
                </td>
                {/* Blank, not zero, for anyone on or over target -- and blank
                    too when linked sessions disagree on a lecturer's variance,
                    since there is then no single figure to publish. */}
                <td className="staff-col-metric staff-col-owed">
                  {row.hours_owed != null ? formatHours(row.hours_owed, 1) : ""}
                </td>
                <td className="staff-col-metric staff-col-owed">
                  {row.hours_owed_after_cover != null ? (
                    row.hours_owed_after_cover === 0 ? (
                      <span className="staff-owed-clear" title="Cover has cleared what they owed">
                        0
                      </span>
                    ) : (
                      formatHours(row.hours_owed_after_cover, 1)
                    )
                  ) : (
                    ""
                  )}
                </td>
                <td className="staff-col-meta staff-hours-wrap">{row.cost_centre ?? ""}</td>
                <td className="staff-col-metric staff-col-metric-group">
                  {formatFte(row.fte)}
                </td>
                <td className="staff-col-metric">{formatCurrentFte(row.total_hours)}</td>
                <td className="staff-col-metric">{formatLecturingHours(row.lecturing_hours)}</td>
                <td className="staff-col-metric staff-col-metric-highlight">
                  {formatHours(row.in_class_timetabled_hours)}
                </td>
                <td
                  className="staff-col-meta staff-hours-truncate"
                  title={row.session_schedule_avg ?? undefined}
                >
                  {row.session_schedule_avg ?? "—"}
                </td>
                <td className="staff-col-detail staff-hours-bulk-online-col">
                  <BulkOnlineCell
                    detail={row.bulk_online_detail}
                    rowId={row.id}
                    expanded={expandedBulkIds.has(row.id)}
                    onToggle={toggleBulkExpanded}
                  />
                </td>
                <td className="staff-col-metric">{formatHours(row.bulk_online_hours_avg)}</td>
                <td className="staff-col-meta staff-col-meta-group">
                  {formatOptionalNum(row.development_project_hours)}
                </td>
                <td className="staff-col-meta staff-hours-wrap">
                  {row.development_project_description ?? ""}
                </td>
                <td className="staff-col-meta">{formatOptionalNum(row.tae_hours)}</td>
                <td className="staff-col-meta">{formatOptionalNum(row.supervision_hours)}</td>
                <td className="staff-col-meta">
                  {row.non_teaching_day != null &&
                  row.non_teaching_day >= 0 &&
                  row.non_teaching_day < 5
                    ? DAY_LABELS[row.non_teaching_day]
                    : "—"}
                </td>
                <td className="staff-col-meta staff-col-meta-group staff-hours-wrap">
                  {row.preferences_first}
                </td>
                <td className="staff-col-meta staff-hours-wrap">{row.preferences_second}</td>
                <td className="staff-col-meta staff-hours-wrap">{row.preferences_third}</td>
              </tr>
            ))}
            {!loading && !filtered.length && (
              <tr>
                <td colSpan={20} className="staff-hours-empty">
                  {rows.length
                    ? search.trim() || varianceFilter !== "all"
                      ? "No lecturers match the current filters."
                      : "No staff in this session."
                    : "No staff in this session."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
        </>
      )}
    </div>
  );
}

import { useMemo, useState } from "react";
import type { StaffHoursRow } from "../types";
import {
  formatHours,
  formatOptionalNum,
  VARIANCE_FILTER_OPTIONS,
  varianceCellClass,
  varianceTooltip,
  type StaffVarianceCategory,
} from "../lib/staffVariance";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

type Props = {
  rows: StaffHoursRow[];
  selectedId: number | null;
  onSelect: (staffId: number) => void;
  loading?: boolean;
};

export function StaffHoursTable({ rows, selectedId, onSelect, loading }: Props) {
  const [varianceFilter, setVarianceFilter] = useState<"all" | StaffVarianceCategory>("all");

  const filtered = useMemo(() => {
    if (varianceFilter === "all") return rows;
    return rows.filter((r) => r.variance_category === varianceFilter);
  }, [rows, varianceFilter]);

  return (
    <div className="staff-hours-table-wrap">
      <div className="staff-hours-table-toolbar">
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
        <span className="muted staff-hours-table-count">
          {filtered.length} of {rows.length} lecturer{rows.length === 1 ? "" : "s"}
        </span>
      </div>
      {loading && <p className="muted">Loading hours…</p>}
      <div className="staff-hours-table-scroll">
        <table className="staff-hours-table">
          <thead>
            <tr>
              <th>Lecturer</th>
              <th>FTE</th>
              <th title="FTE × 21 hours per FTE">Lecturing h</th>
              <th title="Weekly in-class scheduled contact (non-online rooms), session-adjusted">
                In-class h
              </th>
              <th title="Sessions × hours ÷ 20 weeks when class runs fewer than all semester weeks">
                Session avg
              </th>
              <th title="Total workload minus lecturing hours">Variance</th>
              <th title="Per-class online session detail">Bulk online</th>
              <th title="Online / collaborate load hours">Bulk online h</th>
              <th>Dev &amp; project</th>
              <th>Dev description</th>
              <th>PD / training</th>
              <th>Supervision</th>
              <th title="In-class + bulk online + dev + PD + supervision">Total</th>
              <th>Non-teach day</th>
              <th>1st prefs</th>
              <th>2nd prefs</th>
              <th>3rd prefs</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr
                key={row.id}
                className={selectedId === row.id ? "staff-hours-row selected" : "staff-hours-row"}
                onClick={() => onSelect(row.id)}
              >
                <td className="staff-hours-name">{row.name}</td>
                <td>{formatOptionalNum(row.fte)}</td>
                <td>{formatHours(row.lecturing_hours)}</td>
                <td>{formatHours(row.in_class_timetabled_hours)}</td>
                <td className="staff-hours-wrap staff-hours-truncate" title={row.session_schedule_avg ?? undefined}>
                  {row.session_schedule_avg ?? "—"}
                </td>
                <td
                  className={varianceCellClass(row.variance_category)}
                  title={varianceTooltip(row.variance_category)}
                >
                  {formatHours(row.variance)}
                </td>
                <td
                  className="staff-hours-wrap staff-hours-detail staff-hours-truncate"
                  title={row.bulk_online_detail ?? undefined}
                >
                  {row.bulk_online_detail ?? ""}
                </td>
                <td>{formatHours(row.bulk_online_hours_avg)}</td>
                <td>{formatOptionalNum(row.development_project_hours)}</td>
                <td className="staff-hours-wrap">{row.development_project_description ?? ""}</td>
                <td>{formatOptionalNum(row.tae_hours)}</td>
                <td>{formatOptionalNum(row.supervision_hours)}</td>
                <td>{formatHours(row.total_hours)}</td>
                <td>
                  {row.non_teaching_day != null && row.non_teaching_day >= 0 && row.non_teaching_day < 5
                    ? DAY_LABELS[row.non_teaching_day]
                    : "—"}
                </td>
                <td className="staff-hours-wrap">{row.preferences_first}</td>
                <td className="staff-hours-wrap">{row.preferences_second}</td>
                <td className="staff-hours-wrap">{row.preferences_third}</td>
              </tr>
            ))}
            {!loading && !filtered.length && (
              <tr>
                <td colSpan={17} className="muted staff-hours-empty">
                  {rows.length ? "No lecturers match this variance filter." : "No staff in this session."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

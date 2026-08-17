/** Build an email-pasteable cover list from the pending requests and copy it.
 *
 * The list, not the grid it was built from: what gets emailed is "these are the
 * classes needing cover, here is who is doing each", which is exactly the
 * pending requests table. Reading it off the timetable instead meant the copy
 * only ever held one lecturer's classes in one week, and nothing at all before
 * a lecturer was picked.
 */
import type { CoverRequest } from "../api";
import { formatHours } from "./staffVariance";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

const HEADERS = [
  "Date",
  "Day / Time",
  "Group",
  "Class",
  "Room",
  "Away lecturer",
  "Cover lecturer",
  // Spelled out rather than the screen's "Owed"/"After": the table lands in an
  // email with none of the surrounding page to explain the shorthand.
  "Hours owed",
  "Owed after cover",
];

function hoursCell(hours: number | null | undefined): string {
  return hours == null ? "—" : `${formatHours(hours, 1)}h`;
}

function cells(r: CoverRequest): string[] {
  return [
    r.cover_date ?? "—",
    [r.day_label, r.time_label].filter(Boolean).join(" "),
    r.group_name,
    r.unit_name,
    r.room_code,
    r.away_staff_name,
    // Unassigned is worth saying out loud in an email, not left blank.
    r.cover_staff_name || "Unassigned",
    hoursCell(r.hours_owed_before),
    hoursCell(r.hours_owed_after),
  ];
}

/** Date first, so a multi-week plan reads in the order it happens. */
function sortRows(requests: CoverRequest[]): CoverRequest[] {
  return [...requests].sort((a, b) => {
    const da = a.cover_date ?? "";
    const db = b.cover_date ?? "";
    if (da !== db) return da < db ? -1 : 1;
    return (a.time_label || "").localeCompare(b.time_label || "");
  });
}

function buildHtml(title: string, rows: CoverRequest[]): string {
  const th = (t: string) =>
    `<th style="border:1px solid #ccc;padding:6px 10px;background:#f0f3f8;text-align:left;font-family:Arial,sans-serif;font-size:13px;">${escapeHtml(t)}</th>`;
  const td = (t: string) =>
    `<td style="border:1px solid #ccc;padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;">${escapeHtml(t)}</td>`;

  const body = rows.map((r) => `<tr>${cells(r).map(td).join("")}</tr>`).join("");

  return (
    `<p style="font-family:Arial,sans-serif;font-size:14px;font-weight:bold;margin:0 0 8px;">${escapeHtml(title)}</p>` +
    `<table style="border-collapse:collapse;border:1px solid #ccc;">` +
    `<thead><tr>${HEADERS.map(th).join("")}</tr></thead>` +
    `<tbody>${body}</tbody></table>`
  );
}

function buildPlainText(title: string, rows: CoverRequest[]): string {
  const lines = [title, "", HEADERS.join("\t")];
  for (const r of rows) lines.push(cells(r).join("\t"));
  return lines.join("\n");
}

/**
 * Copies the pending cover requests as a formatted table.
 * Writes both text/html (pastes as a table in email clients) and text/plain
 * (tab-separated fallback). Returns the row count.
 */
export async function copyCoverRequests(
  requests: CoverRequest[],
  title: string,
): Promise<number> {
  const rows = sortRows(requests);
  const html = buildHtml(title, rows);
  const plain = buildPlainText(title, rows);

  if (navigator.clipboard && "write" in navigator.clipboard && typeof ClipboardItem !== "undefined") {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([plain], { type: "text/plain" }),
      }),
    ]);
  } else {
    // Fallback: plain text only
    await navigator.clipboard.writeText(plain);
  }

  return rows.length;
}

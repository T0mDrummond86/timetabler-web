/** Build an email-pasteable cover timetable from a loaded grid and copy it. */
import type { TimetableGrid } from "../types";
import { slotToTimeLabel } from "./timeUtils";

type Row = {
  date: string;
  day: string;
  dayIndex: number;
  start: number;
  time: string;
  group: string;
  unit: string;
  room: string;
  cover: string;
};

function buildRows(grid: TimetableGrid, dateByBookingId: Map<number, string>): Row[] {
  return grid.bookings
    .filter((b) => (b.cover_staff_name ?? "").trim() !== "")
    .map((b) => ({
      date: dateByBookingId.get(b.id) ?? "",
      day: grid.days[b.day] ?? `Day ${b.day + 1}`,
      dayIndex: b.day,
      start: b.start_slot,
      time: `${slotToTimeLabel(b.start_slot)} – ${slotToTimeLabel(b.end_slot)}`,
      group: b.course_code ?? "",
      unit: b.unit_name ?? b.course_code ?? "",
      room: b.room_code ?? "",
      cover: b.cover_staff_name ?? "",
    }))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.dayIndex - b.dayIndex || a.start - b.start));
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

const HEADERS = ["Date", "Day", "Time", "Group", "Class", "Room", "Cover lecturer"];

function buildHtml(title: string, rows: Row[]): string {
  const th = (t: string) =>
    `<th style="border:1px solid #ccc;padding:6px 10px;background:#f0f3f8;text-align:left;font-family:Arial,sans-serif;font-size:13px;">${escapeHtml(t)}</th>`;
  const td = (t: string) =>
    `<td style="border:1px solid #ccc;padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;">${escapeHtml(t)}</td>`;

  const body = rows
    .map(
      (r) =>
        `<tr>${td(r.date || "—")}${td(r.day)}${td(r.time)}${td(r.group)}${td(r.unit)}${td(r.room)}${td(
          r.cover || "—"
        )}</tr>`
    )
    .join("");

  return (
    `<p style="font-family:Arial,sans-serif;font-size:14px;font-weight:bold;margin:0 0 8px;">${escapeHtml(title)}</p>` +
    `<table style="border-collapse:collapse;border:1px solid #ccc;">` +
    `<thead><tr>${HEADERS.map(th).join("")}</tr></thead>` +
    `<tbody>${body}</tbody></table>`
  );
}

function buildPlainText(title: string, rows: Row[]): string {
  const lines = [title, ""];
  lines.push(HEADERS.join("\t"));
  for (const r of rows) {
    lines.push([r.date || "—", r.day, r.time, r.group, r.unit, r.room, r.cover || "—"].join("\t"));
  }
  return lines.join("\n");
}

/**
 * Copies the grid as a formatted table to the clipboard.
 * Writes both text/html (pastes as a table in email clients) and
 * text/plain (tab-separated fallback). Returns the row count.
 */
export async function copyCoverTimetable(
  grid: TimetableGrid,
  title: string,
  dateByBookingId: Map<number, string> = new Map()
): Promise<number> {
  const rows = buildRows(grid, dateByBookingId);
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

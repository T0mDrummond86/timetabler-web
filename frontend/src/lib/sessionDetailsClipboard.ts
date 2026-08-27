/** Copy one scheduled class as a small table, for pasting into an email.
 *
 * The question this answers is "what are the details of that session?" — asked
 * of a lecturer, a head of department, a room booking. Reading them off the
 * placecard by eye and retyping them is where the transcription errors come
 * from, so the card copies itself.
 *
 * Two columns rather than a header row and one long line: a single session
 * reads better down the page, and it drops into an email without needing the
 * width a wide table would want.
 */
import type { BookingCard } from "../types";
import { slotRangeLabel } from "./timeUtils";

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Blank fields are said out loud. An empty cell in an email reads as an
 *  oversight; "Not assigned" reads as the answer to the question. */
function value(v: string | null | undefined, missing = "Not assigned"): string {
  const text = (v ?? "").trim();
  return text || missing;
}

export function sessionDetailRows(booking: BookingCard): [string, string][] {
  const rows: [string, string][] = [
    ["Class", value(booking.unit_name, "Unnamed class")],
    ["Units", value(booking.unit_component_codes, "—")],
    ["Lecturer", value(booking.staff_name)],
    ["Room", value(booking.room_code)],
    ["Day", DAY_LABELS[booking.day] ?? "—"],
    ["Time", slotRangeLabel(booking.start_slot, booking.end_slot)],
  ];

  // Only worth a line when there is one. A group is obvious from the column
  // you right-clicked in the course view, but not in the staff or room views.
  const group = (booking.course_code ?? "").trim();
  if (group) rows.splice(2, 0, ["Group", group]);

  // The second sitting of a double class is a different session at a different
  // time; without this the two copies would be indistinguishable.
  if ((booking.session_part ?? 1) > 1) {
    rows.push(["Session", `Part ${booking.session_part}`]);
  }
  return rows;
}

function buildHtml(rows: [string, string][]): string {
  const cell = (t: string, bold = false) =>
    `<td style="border:1px solid #ccc;padding:6px 10px;font-family:Arial,sans-serif;` +
    `font-size:13px;${bold ? "font-weight:bold;background:#f0f3f8;" : ""}">${escapeHtml(t)}</td>`;
  const body = rows.map(([k, v]) => `<tr>${cell(k, true)}${cell(v)}</tr>`).join("");
  return `<table style="border-collapse:collapse;border:1px solid #ccc;"><tbody>${body}</tbody></table>`;
}

function buildPlainText(rows: [string, string][]): string {
  // Tab-separated, so it still lands as two columns in a spreadsheet.
  return rows.map(([k, v]) => `${k}\t${v}`).join("\n");
}

/** What would go on the clipboard.
 *
 * Split from the write so the payload can be checked without a clipboard: the
 * browser refuses `clipboard.write` outside a focused document with
 * permission, which makes the interesting half of this file otherwise
 * untestable.
 */
export function sessionDetailsPayload(booking: BookingCard): {
  html: string;
  plain: string;
} {
  const rows = sessionDetailRows(booking);
  return { html: buildHtml(rows), plain: buildPlainText(rows) };
}

/**
 * Copies one session's details as a table. Writes both text/html (pastes as a
 * table in email clients) and text/plain (tab-separated fallback).
 */
export async function copySessionDetails(booking: BookingCard): Promise<void> {
  const { html, plain } = sessionDetailsPayload(booking);

  if (
    navigator.clipboard &&
    "write" in navigator.clipboard &&
    typeof ClipboardItem !== "undefined"
  ) {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([plain], { type: "text/plain" }),
      }),
    ]);
    return;
  }
  await navigator.clipboard.writeText(plain);
}

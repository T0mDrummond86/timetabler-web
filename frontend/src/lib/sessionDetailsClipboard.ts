/** Copy one scheduled class as a table row, for pasting into an email.
 *
 * The question this answers is "what are the details of that session?" — asked
 * of a lecturer, a head of department, a room booking. Reading them off the
 * placecard by eye and retyping them is where the transcription errors come
 * from, so the card copies itself.
 *
 * Headers across the top and the session on one row, matching the cover list
 * and the change-log copies. Two sessions pasted one after another then stack
 * into a single readable table instead of two stacks of labels.
 */
import type { BookingCard } from "../types";
import { slotRangeLabel } from "./timeUtils";

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

const HEADERS = ["Class", "Units", "Group", "Lecturer", "Room", "Day", "Time"];

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Blank fields are said out loud. An empty cell in an email reads as an
 *  oversight; "Not assigned" reads as the answer to the question. */
function value(v: string | null | undefined, missing = "Not assigned"): string {
  const text = (v ?? "").trim();
  return text || missing;
}

export function sessionDetailCells(booking: BookingCard): string[] {
  // The second sitting of a double class is a different session at a different
  // time. Carried in the class name rather than as its own column, both to keep
  // the header row the same for every session and because that is how the app
  // labels a part elsewhere.
  const part = (booking.session_part ?? 1) > 1 ? ` (part ${booking.session_part})` : "";

  return [
    value(booking.unit_name, "Unnamed class") + part,
    value(booking.unit_component_codes, "—"),
    value(booking.course_code, "—"),
    value(booking.staff_name),
    value(booking.room_code),
    DAY_LABELS[booking.day] ?? "—",
    slotRangeLabel(booking.start_slot, booking.end_slot),
  ];
}

function buildHtml(cells: string[]): string {
  const th = (t: string) =>
    `<th style="border:1px solid #ccc;padding:6px 10px;background:#f0f3f8;text-align:left;` +
    `font-family:Arial,sans-serif;font-size:13px;">${escapeHtml(t)}</th>`;
  const td = (t: string) =>
    `<td style="border:1px solid #ccc;padding:6px 10px;font-family:Arial,sans-serif;` +
    `font-size:13px;">${escapeHtml(t)}</td>`;

  return (
    `<table style="border-collapse:collapse;border:1px solid #ccc;">` +
    `<thead><tr>${HEADERS.map(th).join("")}</tr></thead>` +
    `<tbody><tr>${cells.map(td).join("")}</tr></tbody></table>`
  );
}

function buildPlainText(cells: string[]): string {
  // Tab-separated, so it lands as columns in a spreadsheet.
  return [HEADERS.join("\t"), cells.join("\t")].join("\n");
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
  const cells = sessionDetailCells(booking);
  return { html: buildHtml(cells), plain: buildPlainText(cells) };
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

/** Copy logged changes to the clipboard, formatted for pasting into an email. */
import type { ChangeLogRow } from "../types";

type Fields = {
  group: string;
  cls: string;
  lecturer: string;
  time: string;
  day: string;
  room: string;
  when: string;
  action: string;
  note: string;
};

function fieldsOf(r: ChangeLogRow): Fields {
  return {
    group: r.row.group ?? "",
    cls: r.row.class ?? "",
    lecturer: r.row.lecturer_change ?? "",
    time: r.row.time_change ?? "",
    day: r.row.day_change ?? "",
    room: r.row.room_change ?? "",
    when: r.when ?? "",
    action: r.removed ? `${r.action} (removed)` : r.action,
    note: r.note ?? "",
  };
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function writeClipboard(html: string, plain: string): Promise<void> {
  if (navigator.clipboard && "write" in navigator.clipboard && typeof ClipboardItem !== "undefined") {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([plain], { type: "text/plain" }),
      }),
    ]);
  } else {
    await navigator.clipboard.writeText(plain);
  }
}

const HEADERS = ["Group", "Class", "Lecturer", "Time", "Day", "Room"] as const;

/** Copy a set of logged changes as an HTML table (with a tab-separated fallback). */
export async function copyChangeLogRows(rows: ChangeLogRow[]): Promise<number> {
  const data = rows.map(fieldsOf);
  const hasNote = data.some((f) => f.note.trim() !== "");
  const headers = hasNote ? [...HEADERS, "Note"] : [...HEADERS];
  const cells = (f: Fields): string[] => {
    const base = [f.group, f.cls, f.lecturer, f.time, f.day, f.room];
    return hasNote ? [...base, f.note] : base;
  };

  const th = (t: string) =>
    `<th style="border:1px solid #ccc;padding:6px 10px;background:#f0f3f8;text-align:left;font-family:Arial,sans-serif;font-size:13px;">${escapeHtml(t)}</th>`;
  const td = (t: string) =>
    `<td style="border:1px solid #ccc;padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;">${escapeHtml(t || "—")}</td>`;
  const body = data
    .map((f) => `<tr>${cells(f).map(td).join("")}</tr>`)
    .join("");
  const html =
    `<table style="border-collapse:collapse;border:1px solid #ccc;">` +
    `<thead><tr>${headers.map(th).join("")}</tr></thead>` +
    `<tbody>${body}</tbody></table>`;

  const plainLines = [headers.join("\t")];
  for (const f of data) plainLines.push(cells(f).map((c) => c || "—").join("\t"));

  await writeClipboard(html, plainLines.join("\n"));
  return rows.length;
}

/** Copy a single logged change as a one-row table (same format as copy-all). */
export async function copyChangeLogRow(row: ChangeLogRow): Promise<void> {
  await copyChangeLogRows([row]);
}

const LECTURER_HEADERS = [
  "Affected lecturers",
  "Group",
  "Class",
  "Lecturer",
  "Time",
  "Day",
  "Room",
] as const;

/**
 * Copies the active (non-removed) changes as a table that names every lecturer
 * each change touches — including changes that were not lecturer swaps, so a
 * room or time move still shows who has to be told. Returns the row count.
 */
export async function copyChangeLogLecturerTable(rows: ChangeLogRow[]): Promise<number> {
  const active = rows.filter((r) => !r.removed);
  const data = active.map((r) => ({
    lecturers: (r.lecturers ?? []).join(", "),
    ...fieldsOf(r),
  }));
  const hasNote = data.some((f) => f.note.trim() !== "");
  const headers = hasNote ? [...LECTURER_HEADERS, "Note"] : [...LECTURER_HEADERS];
  const cells = (f: (typeof data)[number]): string[] => {
    const base = [f.lecturers, f.group, f.cls, f.lecturer, f.time, f.day, f.room];
    return hasNote ? [...base, f.note] : base;
  };

  const th = (t: string) =>
    `<th style="border:1px solid #ccc;padding:6px 10px;background:#f0f3f8;text-align:left;font-family:Arial,sans-serif;font-size:13px;">${escapeHtml(t)}</th>`;
  const td = (t: string, first: boolean) =>
    `<td style="border:1px solid #ccc;padding:6px 10px;font-family:Arial,sans-serif;font-size:13px;${first ? "font-weight:bold;white-space:nowrap;" : ""}">${escapeHtml(t || "—")}</td>`;
  const body = data
    .map((f) => `<tr>${cells(f).map((c, i) => td(c, i === 0)).join("")}</tr>`)
    .join("");
  const html =
    `<table style="border-collapse:collapse;border:1px solid #ccc;">` +
    `<thead><tr>${headers.map(th).join("")}</tr></thead>` +
    `<tbody>${body}</tbody></table>`;

  const plainLines = [headers.join("\t")];
  for (const f of data) plainLines.push(cells(f).map((c) => c || "—").join("\t"));

  await writeClipboard(html, plainLines.join("\n"));
  return active.length;
}

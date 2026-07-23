/** Copy the loaded week grid as a basic email-pasteable timetable table. */
import type { BookingCard, TimetableGrid } from "../types";
import { slotToTimeLabel } from "./timeUtils";

type Block = {
  start: number;
  end: number;
  bookings: BookingCard[];
};

/** Merge a day's bookings into non-overlapping blocks (clashes share a cell). */
function dayBlocks(bookings: BookingCard[]): Block[] {
  const sorted = [...bookings].sort((a, b) => a.start_slot - b.start_slot || a.end_slot - b.end_slot);
  const blocks: Block[] = [];
  for (const b of sorted) {
    const last = blocks[blocks.length - 1];
    if (last && b.start_slot < last.end) {
      last.end = Math.max(last.end, b.end_slot);
      last.bookings.push(b);
    } else {
      blocks.push({ start: b.start_slot, end: b.end_slot, bookings: [b] });
    }
  }
  return blocks;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const FONT = "font-family:Arial,sans-serif;font-size:12px;";

/** "T1"/"T2" for a class that runs one term only — matches the placecard badge.
 *  Empty when it runs both terms (or the flags aren't set). */
function termLabel(b: BookingCard): string {
  const t1 = Boolean(b.in_term_1);
  const t2 = Boolean(b.in_term_2);
  if (t1 === t2) return "";
  return t1 ? "T1" : "T2";
}

function cellContent(block: Block): string {
  return block.bookings
    .map((b) => {
      const term = termLabel(b);
      const lines = [
        `<strong>${escapeHtml(b.unit_name ?? b.course_code ?? "Class")}</strong>` +
          (term
            ? ` <span style="font-weight:bold;color:#b45309;">(${escapeHtml(term)} only)</span>`
            : ""),
        escapeHtml(`${slotToTimeLabel(b.start_slot)} – ${slotToTimeLabel(b.end_slot)}`),
      ];
      if (b.staff_name) lines.push(escapeHtml(b.staff_name));
      if (b.room_code) lines.push(escapeHtml(b.room_code));
      return lines.join("<br>");
    })
    .join("<br><br>");
}

/**
 * Copies the grid as a day × time table: day columns, half-hour rows, classes
 * as rowspan cells. Writes text/html (pastes as a table in email clients) and
 * a text/plain day-by-day listing as fallback. Returns the booking count.
 */
export async function copyTimetableGrid(grid: TimetableGrid, title: string): Promise<number> {
  const bookings = grid.bookings;
  if (!bookings.length) return 0;

  const days = grid.days.map((label, i) => ({
    label,
    blocks: dayBlocks(bookings.filter((b) => b.day === i)),
  }));
  const minSlot = Math.min(...bookings.map((b) => b.start_slot));
  const maxSlot = Math.max(...bookings.map((b) => b.end_slot));

  const th = (t: string, width = "") =>
    `<th style="border:1px solid #ccc;padding:4px 8px;background:#f0f3f8;text-align:left;${FONT}${width}">${escapeHtml(t)}</th>`;
  const timeTd = (t: string) =>
    `<td style="border:1px solid #ccc;padding:2px 6px;background:#f7f8fb;white-space:nowrap;${FONT}color:#666;">${escapeHtml(t)}</td>`;
  const emptyTd = `<td style="border:1px solid #eee;padding:2px 6px;"></td>`;
  const blockTd = (block: Block) =>
    `<td rowspan="${block.end - block.start}" style="border:1px solid #ccc;padding:4px 8px;background:#eef4ff;vertical-align:top;${FONT}">${cellContent(block)}</td>`;

  const bodyRows: string[] = [];
  for (let slot = minSlot; slot < maxSlot; slot++) {
    const cells: string[] = [timeTd(slotToTimeLabel(slot))];
    for (const day of days) {
      const starting = day.blocks.find((bl) => bl.start === slot);
      if (starting) {
        cells.push(blockTd(starting));
      } else if (!day.blocks.some((bl) => bl.start < slot && slot < bl.end)) {
        cells.push(emptyTd);
      }
      // Slots inside a block emit nothing — covered by the rowspan above.
    }
    bodyRows.push(`<tr style="height:14px;">${cells.join("")}</tr>`);
  }

  const html =
    `<p style="${FONT}font-size:14px;font-weight:bold;margin:0 0 8px;">${escapeHtml(title)}</p>` +
    `<table style="border-collapse:collapse;border:1px solid #ccc;">` +
    `<thead><tr>${th("Time", "width:56px;")}${days.map((d) => th(d.label)).join("")}</tr></thead>` +
    `<tbody>${bodyRows.join("")}</tbody></table>`;

  const plainLines: string[] = [title, ""];
  for (const day of days) {
    if (!day.blocks.length) continue;
    plainLines.push(`${day.label}:`);
    for (const bl of day.blocks) {
      for (const b of bl.bookings) {
        const term = termLabel(b);
        const name = b.unit_name ?? b.course_code ?? "Class";
        plainLines.push(
          `  ${slotToTimeLabel(b.start_slot)} – ${slotToTimeLabel(b.end_slot)}  ` +
            [term ? `${name} (${term} only)` : name, b.staff_name, b.room_code]
              .filter(Boolean)
              .join(" — "),
        );
      }
    }
    plainLines.push("");
  }

  const plain = plainLines.join("\n").trimEnd();
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
  return bookings.length;
}

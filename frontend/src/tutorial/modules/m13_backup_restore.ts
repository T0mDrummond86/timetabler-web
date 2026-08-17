/** Module 13 — export the full timetable to Excel, then restore from it.
 *
 * The Excel export doubles as the backup format: the workbook that goes out to
 * be read is the same one the importer can rebuild a session from. Closing the
 * loop hands the learner their safety net.
 */
import { api } from "../../api";
import type { TutorialModule } from "../types";

export const m13BackupRestore: TutorialModule = {
  id: "m13_backup_restore",
  title: "Backup & restore",
  section: "Tutorial 2 — Running the timetable",
  goal: "Round-trip the whole session through an Excel workbook.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=timetable`,
  steps: [
    {
      id: "export-timetable",
      title: "Export the full timetable",
      body:
        "Open Export ▾ and choose \"Timetable\". The workbook that downloads is the complete session — every course's week grid, staff, rooms, classes and qualifications.\n\nKeep track of where it lands: you're about to feed it back in.",
      advance: "verify",
      target: "export-menu",
      watch: { api: /\/export\/timetable/ },
      eventOnly: true,
      verify: () => true,
      hint: "Export ▾ (top toolbar) → Timetable. It downloads as an .xlsx workbook.",
    },
    {
      id: "whats-inside",
      title: "One workbook, two jobs",
      body:
        "Open it in Excel if you're curious: one visual tab per course, plus data tabs carrying everything the app knows about the session.\n\nThat second part is the point — this isn't just a printout, it's a complete copy. Emailed to a colleague, filed at the end of term, or kept before a risky restructure, it can be turned back into a working session.",
      advance: "next",
    },
    {
      id: "restore-it",
      title: "Restore from the workbook",
      body:
        "Prove it: open Import ▾ and choose \"Session backup\", then pick the workbook you just exported.\n\nThe session is rebuilt from the file — same classes, same placements. Anything you'd changed since the export would be rolled back to what the workbook holds, which is precisely what you want from a backup.",
      advance: "verify",
      target: "import-menu",
      watch: { api: /\/import$/ },
      eventOnly: true,
      // A restore replaces every row, so cached entity ids are stale — the
      // course id must be re-resolved by name before asking for its grid.
      verify: async (ctx) => {
        const info = await api.tutorialInfo(ctx.sessionId);
        const courseId = info.entities.courses?.["CYB-A"];
        if (courseId == null) return false;
        const grid = await api.timetable(ctx.sessionId, {
          view: "course",
          courseId,
          clashDetect: "off",
        });
        return grid.bookings.length > 0;
      },
      hint: "Import ▾ → Session backup → choose the exported .xlsx. The report counts what was restored; the grid should look exactly as it did.",
    },
  ],
  recap: [
    "Export ▾ → Timetable writes the whole session to one workbook.",
    "Import ▾ → Session backup rebuilds the session from that file.",
    "Export before anything risky — the workbook is your undo of last resort.",
  ],
};

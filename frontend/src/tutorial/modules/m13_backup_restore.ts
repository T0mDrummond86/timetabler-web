/** Module 13 — export the full timetable to Excel, then restore from it.
 *
 * The Excel export doubles as the backup format. Restoring an untouched
 * session proves nothing the learner can see, so the module has them break
 * the timetable between export and restore — the restore then visibly undoes
 * real damage, which is the whole point of a backup.
 */
import { api } from "../../api";
import type { TutorialModule, VerifyCtx } from "../types";

/** The class the learner deletes and the restore brings back. */
const SACRIFICE = "Secure Programming Basics";

async function cybAHasSacrifice(ctx: VerifyCtx): Promise<boolean | null> {
  // Entity ids change across a restore, so re-resolve the course by name.
  const info = await api.tutorialInfo(ctx.sessionId);
  const courseId = info.entities.courses?.["CYB-A"];
  if (courseId == null) return null;
  const grid = await api.timetable(ctx.sessionId, {
    view: "course",
    courseId,
    clashDetect: "off",
  });
  return grid.bookings.some((b) => (b.unit_name ?? "").includes(SACRIFICE));
}

export const m13BackupRestore: TutorialModule = {
  id: "m13_backup_restore",
  title: "Backup & restore",
  section: "Tutorial 2 — Running the timetable",
  goal: "Export a backup, break the timetable, and restore it good as new.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=timetable`,
  steps: [
    {
      id: "export-timetable",
      title: "Export the full timetable",
      body:
        "Open Export ▾ and choose \"Timetable\". The workbook that downloads is the complete session — every course's week grid, staff, rooms, classes and qualifications.\n\nIt reads as a printout, but it's a complete copy: the same file can be turned back into a working session. Keep track of where it lands — you're about to need it.",
      advance: "verify",
      target: "export-menu",
      watch: { api: /\/export\/timetable/ },
      eventOnly: true,
      verify: () => true,
      hint: "Export ▾ (top toolbar) → Timetable. It downloads as an .xlsx workbook.",
    },
    {
      id: "break-something",
      title: "Now break something",
      body:
        "A backup only means something once there's damage to undo — so do some damage on purpose. On CYB-A's timetable, right-click Secure Programming Basics (Tuesday morning) and delete the placecard.\n\nGone. On any ordinary day that's a mistake someone made at 4pm on a Friday.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => (await cybAHasSacrifice(ctx)) === false,
      hint: "Timetable tab → Courses view → CYB-A → right-click the Tuesday 09:00 Secure Programming Basics card → Delete placecard. (It leaves the grid entirely — this is more than moving it to the holding area.)",
    },
    {
      id: "restore-it",
      title: "Restore from the workbook",
      body:
        "Open Import ▾ and choose \"Session backup\", then pick the workbook you exported two steps ago.\n\nThe session is rebuilt from the file — and Secure Programming Basics is back on Tuesday morning as if nothing happened. Everything since the export is rolled back to what the workbook holds, which is exactly what you want from a backup.",
      advance: "verify",
      target: "import-menu",
      watch: { api: /\/import$/ },
      eventOnly: true,
      verify: async (ctx) => (await cybAHasSacrifice(ctx)) === true,
      hint: "Import ▾ → Session backup → choose the exported .xlsx. When the import finishes, check Tuesday morning on CYB-A — the deleted class is back.",
    },
  ],
  recap: [
    "Export ▾ → Timetable writes the whole session to one workbook.",
    "Import ▾ → Session backup rebuilds the session from that file — deletions and all.",
    "Export before anything risky — the workbook is your undo of last resort.",
  ],
};

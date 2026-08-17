/** Module 11 — the admin export, and how changes surface in red.
 *
 * The admin export is the workbook the administration actually reads, so the
 * lesson is not "press export" but "your edits are marked up in red when it
 * gets there" — which is what makes the change log worth keeping honest.
 */
import { api } from "../../api";
import type { TutorialModule } from "../types";

export const m11AdminExport: TutorialModule = {
  id: "m11_admin_export",
  title: "Changes in red — the admin export",
  section: "Tutorial 2 — Running the timetable",
  goal: "Make a change, export the admin workbook, and find it marked in red.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=timetable`,
  steps: [
    {
      id: "make-a-change",
      title: "Change something",
      body:
        "The admin export compares the timetable against the change log, so first give it something to mark: move any class to a different time, or swap its lecturer or room.\n\nIf you've worked through earlier modules the log already has entries — make one more move anyway so you know exactly what to look for in the workbook.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => {
        const log = await api.changeLog(ctx.sessionId, true);
        return log.rows.length > 0;
      },
      hint: "Timetable tab → drag any placed class to a free slot, or double-click it and change the room. The Change log tab records it as a resolved change.",
    },
    {
      id: "run-admin-export",
      title: "Run the admin export",
      body:
        "Open Export ▾ and choose \"Admin export\". The workbook that downloads is the term-week grid administrators work from — one tab per course.\n\nEvery class whose time, lecturer or room differs from the original timetable has that cell filled red, and if a class moved to a different weekday, the day header is red too. Nobody has to diff two timetables by eye — the red is the diff.",
      advance: "verify",
      target: "export-menu",
      watch: { api: /\/export\/admin/ },
      eventOnly: true,
      verify: () => true,
      hint: "Export ▾ (top toolbar) → Admin export. It lands in your downloads as admin_export.xlsx.",
    },
    {
      id: "read-the-red",
      title: "Open it and find the red",
      body:
        "Open the workbook in Excel and find the class you moved: the changed TIME, Lecturer or Room cell is filled red on that course's tab.\n\nWhen the term is in full swing and the log is long, \"Admin export (changes only)\" exports just the courses that changed — the administration reads five tabs instead of fifty.",
      advance: "next",
    },
  ],
  recap: [
    "The admin export is the administration's term-week grid, one tab per course.",
    "Cells that differ from the original timetable — time, lecturer, room — are filled red.",
    "Admin export (changes only) trims the workbook to just the courses that changed.",
  ],
};

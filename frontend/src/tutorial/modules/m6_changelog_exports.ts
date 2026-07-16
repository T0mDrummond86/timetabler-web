/** Module 6 — Change log & exports. */
import type { TutorialModule } from "../types";
import { urlTab } from "../verifyHelpers";

export const m6ChangelogExports: TutorialModule = {
  id: "m6_changelog_exports",
  title: "Change log & exports",
  goal: "Trace your edits and hand the timetable to the outside world.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=changelog`,
  steps: [
    {
      id: "open-changelog",
      title: "Open the Change log",
      body:
        "Every fix you've made this session was recorded. Open the Change log tab and browse it.",
      advance: "verify",
      target: "tab-changelog",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "changelog",
    },
    {
      id: "resolved-view",
      title: "Full log vs Resolved",
      body:
        "The Full log shows every individual edit (including undos). Switch to Resolved to see only the net result per class — what actually changed since the start. Resolved rows take notes for your records, can be exported to Excel, and offer per-booking rollback.",
      advance: "next",
    },
    {
      id: "run-export",
      title: "Run an export",
      body:
        "Timetables leave this app constantly — to Excel workbooks, admin grids, staff-hour sheets and PDF prints. Open Export ▾ on the Timetable tab's toolbar and run one now (Staff tab is the quickest — a lecturer-hours spreadsheet lands in your downloads).",
      advance: "verify",
      target: "export-menu",
      watch: { api: /\/export\// },
      eventOnly: true,
      verify: () => true,
      hint: "Timetable tab → Export ▾ (top toolbar) → 'Staff tab'. Any export in the menu completes this step.",
    },
  ],
  recap: [
    "The Change log records every edit; Resolved shows the net changes with notes and rollback.",
    "Export ▾ covers Excel workbooks, admin grids, staff hours, PDFs and backups.",
  ],
};

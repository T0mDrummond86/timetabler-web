/** Module 10 — import a filled-in lecturer preferences workbook.
 *
 * The workbook is how lecturer voice reaches the timetable: class preferences,
 * a non-teaching day, and blocked times, collected per lecturer and imported
 * in one go. The sample is pre-filled for two sandbox lecturers.
 */
import { api } from "../../api";
import type { TutorialModule } from "../types";
import { urlTab } from "../verifyHelpers";

export const m10PreferencesImport: TutorialModule = {
  id: "m10_preferences_import",
  title: "Lecturer preferences",
  section: "Tutorial 2 — Running the timetable",
  goal: "Import a preferences workbook and see it land on the staff profiles.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=timetable`,
  steps: [
    {
      id: "the-workbook",
      title: "How preferences are collected",
      body:
        "Each semester you send lecturers a preferences workbook — one tab per lecturer, with dropdowns for the classes they'd like to teach (first, second and third preference), their non-teaching day, and a grid to cross out times they can't work.\n\nExport ▾ → \"Lecturer preferences template\" makes a blank one from your real staff list. For this exercise, download the pre-filled sample below — Keanu Reeves and Stephen Hawking have already answered. Open it and look around before importing.",
      advance: "next",
      download: {
        label: "Download the filled-in sample (.xlsx)",
        kind: "preferences",
        filename: "Lecturer preferences (tutorial sample).xlsx",
      },
    },
    {
      id: "run-the-import",
      title: "Import it",
      body:
        "Open Import ▾ and choose \"Lecturer preferences\", then pick the downloaded workbook.\n\nFor every lecturer sheet it finds, the import replaces that lecturer's stored preferences, sets their non-teaching day, and rewrites their availability from the blocked-times grid. Lecturers without a sheet are left alone.",
      advance: "verify",
      target: "import-menu",
      watch: { api: /\/import\// },
      verify: async (ctx) => {
        const staffId = ctx.entities.staff["Keanu Reeves"];
        if (staffId == null) return false;
        const detail = await api.staffDetail(ctx.sessionId, staffId);
        return detail.preferences.first.length > 0 && detail.non_teaching_day === 4;
      },
      hint: "Import ▾ → Lecturer preferences → choose the sample workbook. The report counts staff updated and preferences imported.",
    },
    {
      id: "see-the-result",
      title: "Where it landed",
      body:
        "Open the Staff tab and select Keanu Reeves. His profile now shows the class preferences from the workbook, Friday as his non-teaching day, and evenings blocked out of his availability.\n\nFrom now on, scheduling him after 18:00 raises a warning, a Friday class raises a warning, and his preferences are on hand whenever you're deciding who takes a class.",
      advance: "verify",
      target: "tab-staff",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "staff",
    },
  ],
  recap: [
    "Export ▾ makes the blank template; Import ▾ → Lecturer preferences reads the answers back.",
    "Each sheet replaces that lecturer's preferences, non-teaching day and availability.",
    "Blocked times and non-teaching days turn into warnings the moment a class lands on them.",
  ],
};

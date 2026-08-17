/** Module 14 — the shared cover log, seen from the workspace.
 *
 * First of the global modules. Its prepare hook creates the second-campus
 * sandbox, so from here on the tutorial workspace genuinely has two linked
 * timetables — the thing every global feature exists to serve.
 */
import { api } from "../../api";
import type { TutorialModule, VerifyCtx } from "../types";

/** Both global modules prepare the same way; find-or-create is idempotent. */
export async function prepareCompanion(sessionId: number): Promise<void> {
  await api.tutorialCompanion(sessionId);
}

function onWorkspaceTab(ctx: VerifyCtx, tab: string): boolean {
  return ctx.url.pathname.startsWith("/global/") && ctx.url.params.get("tab") === tab;
}

export const m14GlobalCover: TutorialModule = {
  id: "m14_global_cover",
  title: "The shared cover log",
  section: "Tutorial 3 — The global workspace",
  goal: "Push a cover job to the log, then read it where the whole team does.",
  prepare: prepareCompanion,
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=lecturer_cover`,
  steps: [
    {
      id: "meet-the-workspace",
      title: "Your sandbox grew a second campus",
      body:
        "A global workspace groups timetable sessions that share people and records — campuses timetabled separately, one department in fact.\n\nStarting this module created \"campus 2\": a second sandbox in your tutorial workspace, with Serena Williams and Nelson Mandela teaching at both. Everything in this tutorial works across the two.\n\nThe cover log is the first shared record: sessions push confirmed cover jobs to it, and the workspace reads them in one place.",
      advance: "next",
    },
    {
      id: "push-a-job",
      title: "Push a cover job to the log",
      body:
        "On the Lecturer cover tab, get one request ready and push it: pick a lecturer needing cover, double-click one of their classes with a cover lecturer selected, then press \"Push to log\" on the request.\n\nIf you finished the cover-routine module, the log already has your job — this step recognises that and passes.",
      advance: "verify",
      target: "tab-lecturer_cover",
      watch: { api: /\/cover-requests|\/cover-log/ },
      verify: async (ctx) => {
        const info = await api.tutorialInfo(ctx.sessionId);
        if (info.global_session_id == null) return false;
        const log = await api.coverLog(info.global_session_id);
        return log.entries.length > 0;
      },
      hint: "Lecturer cover tab → choose Cathy Freeman → click her Monday class once → pick Nelson Mandela as cover → double-click the class → Push to log on the request row.",
    },
    {
      id: "read-it-in-the-workspace",
      title: "Read it where the team does",
      body:
        "Now see it from the other side. Open your tutorial workspace — the workspace name in the sidebar links there — and open its Cover log tab.\n\nEvery entry names the class, the date, who was away, who covered, the hours credited, and which session it came from. When both campuses push their jobs here, this one table is the department's cover record.",
      advance: "verify",
      target: "gtab-cover_log",
      watch: { url: true },
      verify: (ctx) => onWorkspaceTab(ctx, "cover_log"),
      hint: "Timetable sidebar → click the workspace name (Tutorial group — …) → Cover log tab. Or Dashboard → the workspace card.",
    },
  ],
  recap: [
    "A workspace groups sessions that share lecturers and records.",
    "Sessions push confirmed cover jobs; the workspace's Cover log tab is the single record.",
    "Logged hours feed the cover ledger on the workspace's Staff tab.",
  ],
};

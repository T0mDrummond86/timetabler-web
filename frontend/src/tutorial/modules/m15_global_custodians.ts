/** Module 15 — class custodians across campuses.
 *
 * The custodian list answers "who owns this class?" — and the global version
 * answers it across every session at once, which is where it earns its keep:
 * the same class taught at two campuses is still one class to the curriculum.
 */
import { api } from "../../api";
import type { TutorialModule, VerifyCtx } from "../types";
import { prepareCompanion } from "./m14_global_cover";

function onWorkspaceTab(ctx: VerifyCtx, tab: string): boolean {
  return ctx.url.pathname.startsWith("/global/") && ctx.url.params.get("tab") === tab;
}

export const m15GlobalCustodians: TutorialModule = {
  id: "m15_global_custodians",
  title: "Class custodians across campuses",
  section: "Tutorial 3 — The global workspace",
  goal: "Work through the global custodian list and pin one by hand.",
  prepare: prepareCompanion,
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=custodians`,
  steps: [
    {
      id: "open-global-list",
      title: "Open the workspace custodian list",
      body:
        "A class's custodian is the lecturer who owns it — keeps the materials current, answers for its delivery. By default that's whoever teaches it most.\n\nOpen your tutorial workspace and its Class custodians tab. Network Security Fundamentals and Workplace Communication appear from both campuses: same class, one row, with every lecturer who delivers it anywhere.",
      advance: "verify",
      target: "gtab-custodians",
      watch: { url: true },
      verify: (ctx) => onWorkspaceTab(ctx, "custodians"),
      hint: "Sidebar → the workspace name → Class custodians tab.",
    },
    {
      id: "work-the-list",
      title: "Working through the list",
      body:
        "This is a working document, not just a report. Order by qualification to review one course area at a time; the Units column shows each class's unit codes; and \"Export to Excel\" hands the whole list to whoever needs it outside the app.\n\nUse the Sessions column while you read: a class taught at both campuses shows both, and its custodian should make sense across the pair — not just at one.",
      advance: "next",
    },
    {
      id: "pin-a-custodian",
      title: "Pin a custodian by hand",
      body:
        "The derived custodian is only a default. Workplace Communication is taught by three people across the campuses — decide who should own it, and pin them.\n\nGo back to your sandbox's Class custodians tab and use the row's dropdown to set the custodian yourself. A pinned custodian shows as manual and stays put even when teaching loads shift.",
      advance: "verify",
      target: "tab-custodians",
      watch: { api: /\/custodian/ },
      verify: async (ctx) => {
        const data = await api.classCustodians(ctx.sessionId);
        return data.rows.some((r) => r.custodian_is_manual);
      },
      hint: "Back on the timetable page → Class custodians tab → find Workplace Communication → choose a lecturer in its Custodian dropdown. \"Pinned\" marks it as a manual choice.",
    },
  ],
  recap: [
    "The workspace custodian list merges the same class across every session.",
    "Order by qualification, check the Units column, export to Excel for meetings.",
    "Pin a custodian when the derived one is wrong — pins survive load changes.",
  ],
};

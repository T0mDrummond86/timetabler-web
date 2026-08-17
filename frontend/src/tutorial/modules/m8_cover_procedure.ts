/** Module 8 — the lecturer cover routine, start to finish.
 *
 * Module 5 ends with one cover request created; this one runs the whole weekly
 * procedure: plan a week, email the list, repeat it for the week after, and
 * push an accepted job to the shared log. The sandbox sits in its own private
 * tutorial workspace, so the push lands in a log nobody else reads.
 */
import { api } from "../../api";
import type { TutorialModule } from "../types";
import { urlTab } from "../verifyHelpers";

export const m8CoverProcedure: TutorialModule = {
  id: "m8_cover_procedure",
  title: "The cover routine",
  section: "Tutorial 2 — Running the timetable",
  goal: "Plan a week of cover, email it, roll it forward, and log the result.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=lecturer_cover`,
  steps: [
    {
      id: "brief",
      title: "The weekly cover routine",
      body:
        "When a lecturer is away, the routine is always the same: pick their classes that need covering, choose who steps in, email the plan out, and log each job once it's confirmed.\n\nThe Lecturer cover tab does all of it in one place — and because covering counts toward an under-hours lecturer's owed time, it also shows you who to ask first.",
      advance: "next",
    },
    {
      id: "open-cover-tab",
      title: "Open Lecturer cover",
      body: "Open the Lecturer cover tab from the tab strip.",
      advance: "verify",
      target: "tab-lecturer_cover",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "lecturer_cover",
    },
    {
      id: "plan-a-week",
      title: "Plan a week for Cathy Freeman",
      body:
        "Cathy Freeman is away next week. Choose her as the lecturer requiring cover, and set the Week beginning box to next Monday — every request you create is dated from that Monday plus the day the class falls on.\n\nNow single-click her Monday class (Legal and Ethical Practice), pick a cover lecturer from the dropdown — the ● dot marks under-hours lecturers who owe time, and busy ones say so — then double-click the class to create the request.",
      advance: "verify",
      watch: { api: /\/cover-requests/ },
      verify: async (ctx) => {
        const data = await api.coverRequests(ctx.sessionId);
        return data.requests.some((r) => r.cover_staff_id != null && !!r.cover_date);
      },
      hint: "Lecturer requiring cover → Cathy Freeman. Click the Monday 13:00 class once, choose Nelson Mandela in the Cover lecturer dropdown, then double-click the class. It appears in Pending cover requests with the date already worked out.",
    },
    {
      id: "email-the-list",
      title: "Email the plan",
      body:
        "The pending requests table is the plan — dates, classes, rooms, who's away, who's covering, and what each cover lecturer still owes before and after the job.\n\nPress \"Copy list for email\" and it lands on your clipboard as a table, ready to paste into an email to the lecturers being asked. The owed-hours columns come along too, so the ask explains itself.",
      advance: "next",
    },
    {
      id: "repeat-next-week",
      title: "Roll it forward a week",
      body:
        "If the absence runs longer, you don't rebuild the plan: press \"Repeat next week\" above the requests table. The latest week of the plan is copied forward seven days — same classes, same cover lecturers, new dates — and the Week beginning box moves along with it.",
      advance: "verify",
      watch: { api: /\/cover-requests/ },
      verify: async (ctx) => {
        const data = await api.coverRequests(ctx.sessionId);
        const dates = new Set(data.requests.map((r) => r.cover_date).filter(Boolean));
        return dates.size >= 2;
      },
      hint: "The button sits next to the 'Pending cover requests' heading. One press adds a second week of dated requests.",
    },
    {
      id: "push-to-log",
      title: "Log a confirmed cover",
      body:
        "When a lecturer replies yes, the job stops being a plan and becomes a record: press \"Push to log\" on that request. It moves to the shared cover log — visible in the global workspace's Cover log tab — and the hours credit the cover lecturer's ledger.\n\nYour sandbox has its own private workspace, so nothing you push here touches a real cover log.",
      advance: "verify",
      watch: { api: /\/cover-requests|\/cover-log/ },
      verify: async (ctx) => {
        const info = await api.tutorialInfo(ctx.sessionId);
        if (info.global_session_id == null) return false;
        const log = await api.coverLog(info.global_session_id);
        return log.entries.length > 0;
      },
      hint: "In the requests table, press Push to log on any row that has both a date and a cover lecturer. The row leaves the table — it now lives in the global cover log.",
    },
  ],
  recap: [
    "Plan cover a week at a time: Week beginning + double-click per class.",
    "Copy list for email sends the whole plan, owed hours included.",
    "Repeat next week rolls the latest week forward; Push to log records a confirmed job.",
    "Logged hours credit the cover lecturer's ledger on the Staff tab.",
  ],
};

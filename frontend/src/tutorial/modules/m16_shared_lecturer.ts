/** Module 16 — one lecturer, two campuses.
 *
 * The quiet workhorse of the workspace: when a lecturer teaches in a linked
 * session, their other-campus classes shade out on your grid. This module has
 * the learner find that shading and read it correctly.
 */
import { api } from "../../api";
import type { TutorialModule } from "../types";
import { urlIntParam, urlView } from "../verifyHelpers";
import { prepareCompanion } from "./m14_global_cover";

export const m16SharedLecturer: TutorialModule = {
  id: "m16_shared_lecturer",
  title: "One lecturer, two campuses",
  section: "Tutorial 3 — The global workspace",
  goal: "Find a shared lecturer's unavailable time before booking over it.",
  prepare: prepareCompanion,
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=timetable&view=staff`,
  steps: [
    {
      id: "open-staff-view",
      title: "Open Serena Williams' timetable",
      body:
        "Serena Williams teaches at both campuses. On the Timetable tab, switch the View to Staff and select her.\n\nWhat you're looking at is only this session's side of her week — the question is what the other campus already claims.",
      advance: "verify",
      watch: { url: true },
      verify: (ctx) =>
        urlView(ctx) === "staff" &&
        urlIntParam(ctx, "staff") === ctx.entities.staff["Serena Williams"],
      hint: "Timetable tab → View dropdown → Staff → pick Serena Williams in the list.",
    },
    {
      id: "spot-the-shading",
      title: "Read the shaded block",
      body:
        "Her Tuesday afternoon carries a shaded block: campus 2 has her teaching Network Security Fundamentals 13:00–16:00. The label names the session it comes from.\n\nThat shading is the workspace talking — the lecturer is spoken for, even though nothing in this timetable occupies the slot. Booking her over it would double-book a person, not a room, and no local check would notice without the link.",
      advance: "verify",
      watch: { api: /\/timetable/ },
      verify: async (ctx) => {
        const staffId = ctx.entities.staff["Serena Williams"];
        if (staffId == null) return false;
        const grid = await api.timetable(ctx.sessionId, {
          view: "staff",
          staffId,
          clashDetect: "off",
        });
        const busy = grid.linked_session_busy_slots;
        return !!busy && Object.values(busy).some((slots) => (slots ?? []).length > 0);
      },
      hint: "The grey block sits on Tuesday from 13:00. If you don't see it, make sure you're on Serena Williams' staff view — and that this module created campus 2 (restart the module if in doubt).",
    },
    {
      id: "why-it-matters",
      title: "Where you'll rely on this",
      body:
        "Planning cover, moving a class, or lending a lecturer to another course — check their staff view first and the shaded blocks tell you what the rest of the workspace has already taken.\n\nThe workspace's own Staff tab completes the picture: hours are totalled across every linked session, so a lecturer at target overall shows at target, even if each campus alone looks light.",
      advance: "next",
    },
  ],
  recap: [
    "A shared lecturer's other-campus classes shade out on your staff view.",
    "Shaded time is spoken for — booking over it double-books the person.",
    "The workspace Staff tab totals hours across every linked session.",
  ],
};

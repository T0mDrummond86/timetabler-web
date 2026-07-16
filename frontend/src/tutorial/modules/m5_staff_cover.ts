/** Module 5 — Staff hours, availability & lecturer cover. */
import { api } from "../../api";
import type { TutorialModule } from "../types";
import { noViolation, urlTab } from "../verifyHelpers";

export const m5StaffCover: TutorialModule = {
  id: "m5_staff_cover",
  title: "Staff hours & cover",
  goal: "Balance an overloaded lecturer, respect availability, arrange cover.",
  startUrl: (ctx) => `/timetable/${ctx.sessionId}?tab=staff`,
  steps: [
    {
      id: "spot-overload",
      title: "Priya is over her load",
      body:
        "Open the Staff tab: Priya Sharma is part-time (0.5 FTE ≈ 10.5 h) but carries 12 hours — her variance is red, and the Warnings tab shows a staff hour-cap warning for her.",
      advance: "verify",
      target: "tab-staff",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "staff",
    },
    {
      id: "rebalance",
      title: "Hand a class to James",
      body:
        "Free her up: her Digital Literacy Support class (CHC-A, Wednesday morning, online) is a clean 2-hour handover. Reassign its lecturer to James Taylor.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: (ctx) => noViolation(ctx, "staff_hour_cap"),
      hint: "Timetable tab → Courses view → CHC-A → double-click Digital Literacy Support (Wednesday) → Lecturer → James Taylor → Save. Priya drops to 10 h.",
    },
    {
      id: "availability",
      title: "Respect availability days",
      body:
        "Marcus Webb only works Monday–Wednesday (his availability is recorded on his staff profile), yet Case Management Skills (CHC-A) sits on his Thursday — a staff_unavailable warning. Move that class to Tuesday afternoon.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: (ctx) => noViolation(ctx, "staff_unavailable"),
      hint: "Courses view → CHC-A → drag Case Management Skills from Thursday to Tuesday 15:00 (after First Aid ends; the room stays A2.01, which is free then).",
    },
    {
      id: "cover-request",
      title: "Arrange lecturer cover",
      body:
        "Elena Rodriguez is away next Monday. Open the Lecturer cover tab, choose Elena as the lecturer requiring cover, single-click her Monday class (Legal and Ethical Practice), pick a cover lecturer from the dropdown — busy ones are marked — then double-click the class to create the cover request.",
      advance: "verify",
      target: "tab-lecturer_cover",
      watch: { api: /\/cover-requests/ },
      verify: async (ctx) => {
        const data = await api.coverRequests(ctx.sessionId);
        return data.requests.length > 0;
      },
      hint: "Lecturer cover tab → 'Lecturer requiring cover': Elena Rodriguez → click her Monday 13:00 class once → choose James Taylor as cover → double-click the class. It lands in the requests table below, ready to push to the global log when accepted.",
    },
  ],
  recap: [
    "Variance on the Staff tab shows who's over or under their load.",
    "Availability windows turn out-of-hours bookings into hard warnings.",
    "Cover requests live on the Lecturer cover tab until pushed to the global log.",
  ],
};

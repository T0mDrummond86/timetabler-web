/** Module 4 — Clashes & warnings: find and fix the sandbox's deliberate problems. */
import type { TutorialModule } from "../types";
import { noViolation, urlIntParam, urlTab, urlView } from "../verifyHelpers";

export const m4Clashes: TutorialModule = {
  id: "m4_clashes",
  title: "Clashes & warnings",
  goal: "Read the Warnings tab and fix a double-booking, a wrong room, and more.",
  startUrl: (ctx) =>
    `/timetable/${ctx.sessionId}?tab=timetable&view=staff&staff=${ctx.entities.staff["Tom Nguyen"] ?? ""}`,
  steps: [
    {
      id: "see-clash",
      title: "Look at Tom Nguyen's Monday",
      body:
        "Switch to the Staff view and select Tom Nguyen. His Monday holds two overlapping classes — Network Security (10:00) and Linux Administration (11:00). One lecturer, two rooms, same time: a hard clash.",
      advance: "verify",
      target: "sidebar",
      watch: { url: true },
      verify: (ctx) =>
        urlView(ctx) === "staff" &&
        urlIntParam(ctx, "staff") === ctx.entities.staff["Tom Nguyen"],
    },
    {
      id: "open-warnings",
      title: "Check the Warnings tab",
      body:
        "Open the Warnings tab. Every rule breach on the timetable is listed here — find the staff_double_booking row naming Tom. Clicking a row jumps to the offending booking.",
      advance: "verify",
      target: "tab-warnings",
      watch: { url: true },
      verify: (ctx) => urlTab(ctx) === "warnings",
    },
    {
      id: "fix-clash",
      title: "Fix the double-booking",
      body:
        "Back on the timetable, move CYB-B's Linux Administration off Tom's Monday overlap — drag it to a time when Tom is free (Tuesday morning, say). The warning disappears the moment the clash is gone.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: (ctx) => noViolation(ctx, "staff_double_booking"),
      hint: "In Staff view for Tom (or Course view for CYB-B), drag the Linux Administration card to Tuesday 09:00 — Tom's Tuesday is free until 13:00.",
    },
    {
      id: "fix-room-type",
      title: "Wrong room type",
      body:
        "Linux Administration needs an on-campus room, but it's sitting in ONL-1 (online) — that's the room_type warning. Double-click the card and rehome it to a free on-campus room like B1.04 or A2.01.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: (ctx) => noViolation(ctx, "room_type"),
      hint: "Double-click Linux Administration → Room → pick B1.04 (check its column is free at that time) → Save.",
    },
    {
      id: "fix-capacity",
      title: "Room too small",
      body:
        "Provide First Aid needs 25 seats but is booked into 12-seat A1.10 (Tuesday morning, CHC-A). Move it into A2.02, which seats 30.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: (ctx) => noViolation(ctx, "room_capacity"),
      hint: "Switch the sidebar to Courses → CHC-A, double-click Provide First Aid, set Room to A2.02, Save. (A2.02 is free Tuesday morning.)",
    },
    {
      id: "fix-competency",
      title: "Lecturer not on the allowed list",
      body:
        "David Chen is teaching Secure Programming Basics (CYB-B, Wednesday) but isn't on its allowed-lecturers list — a soft warning. Soft warnings can be dismissed when they're acceptable, but here, reassign the class to James Taylor, who is allowed and lightly loaded.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: (ctx) => noViolation(ctx, "lecturer_not_allowed"),
      hint: "Course view → CYB-B → double-click Secure Programming Basics (Wednesday) → Lecturer → James Taylor → Save.",
    },
    {
      id: "merge-note",
      title: "When a clash is intentional",
      body:
        "Sometimes one lecturer genuinely runs two cohorts together. On a Staff view, right-click a clashing card and choose Merge clashing classes — the cards fuse into one and stop counting as a clash (Unmerge reverses it). Nothing to fix now; just know it's there.",
      advance: "next",
    },
  ],
  recap: [
    "The Warnings tab lists every breach; rows jump to the booking.",
    "Hard warnings (clashes, wrong rooms) need fixing; soft ones can be dismissed.",
    "Fix by moving cards, changing rooms/lecturers — or merge genuinely shared classes.",
  ],
};

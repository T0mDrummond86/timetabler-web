/** Module 7 — Capstone: schedule the CYB-T group, one class at a time.
 *
 * Deliberately staged rather than "here are four classes, good luck". Each
 * class introduces one new consideration — a free slot, then a lecturer who is
 * already busy, then a pair that must stay together — so a wrong placement
 * fails for a reason the reader can name.
 */
import { api } from "../../api";
import type { TutorialModule } from "../types";
import {
  courseBookings,
  holdingUnitNames,
  urlIntParam,
  urlTab,
  urlView,
} from "../verifyHelpers";

/** A course's placed card for this class, matched on name the way the chips are. */
async function placedCard(
  ctx: Parameters<typeof holdingUnitNames>[0],
  courseCode: string,
  needle: string,
) {
  const cards = await courseBookings(ctx, courseCode);
  return cards.find((b) =>
    (b.unit_name ?? "").toLowerCase().includes(needle.toLowerCase()),
  );
}

/** True when no hard warning names this card. */
async function cardIsClashFree(
  ctx: Parameters<typeof holdingUnitNames>[0],
  bookingId: number,
): Promise<boolean> {
  const report = await api.violationsReport(ctx.sessionId, "hard");
  return !report.rows.some((row) => (row.booking_ids ?? []).includes(bookingId));
}

/** How many of a course's holding-area chips carry this class name. */
async function holdingCount(
  ctx: Parameters<typeof holdingUnitNames>[0],
  courseCode: string,
  needle: string,
): Promise<number> {
  const names = await holdingUnitNames(ctx, courseCode);
  return names.filter((n) => n.toLowerCase().includes(needle.toLowerCase())).length;
}

export const m7Capstone: TutorialModule = {
  id: "m7_capstone",
  title: "Capstone",
  goal: "Schedule the CYB-T group, clash-free, one class at a time.",
  startUrl: (ctx) =>
    `/timetable/${ctx.sessionId}?tab=timetable&view=course&course=${ctx.entities.courses["CYB-T"] ?? ""}`,
  steps: [
    {
      id: "brief",
      title: "Your mission",
      body:
        "The CYB-T capstone group has four sessions still waiting in its holding area: Network Security Fundamentals, Workplace Communication, and both halves of the double-session Cyber Incident Response.\n\nWe'll place them one at a time, and each one adds a wrinkle. Nothing here can break anything — reset the sandbox from the ⋯ menu if it gets messy.",
      advance: "next",
    },
    {
      id: "goto-cyb-t",
      title: "Open CYB-T",
      body:
        "Set the sidebar to Courses view and pick CYB-T. Its holding area, under the grid, shows the four waiting chips.",
      advance: "verify",
      target: "sidebar",
      watch: { url: true },
      verify: (ctx) =>
        urlTab(ctx) === "timetable" &&
        urlView(ctx) === "course" &&
        urlIntParam(ctx, "course") === ctx.entities.courses["CYB-T"],
      hint: "Sidebar → View → Courses, then CYB-T in the list below.",
    },
    {
      id: "split-for-capstone",
      title: "Put a lecturer's week beside it",
      body:
        "Before placing anything, open Split Layout ▾ → 2-way side-by-side. Keep CYB-T in one pane and switch the other to Staff view.\n\nThat second pane is what stops you creating a clash: as you drop a class, the lecturer's week redraws instantly and you see whether they were already busy.\n\nOne thing to know: the split screen has no holding area. You place each class from the holding area in the normal timetable view, then come back here — or keep both open in separate browser tabs — to check the lecturer as you go.",
      advance: "next",
      target: "split-layout",
      hint: "Split Layout ▾ is in the top toolbar. In the new pane, set View to Staff and pick a lecturer. Use 'Back to single view' to reach the holding area again.",
    },
    {
      id: "place-netsec",
      title: "1 of 3 — an easy one first",
      body:
        "Drag Network Security Fundamentals out of the holding area onto a free CYB-T slot. Monday and Thursday afternoons are wide open.\n\nGive it a lecturer and a lab room (B1.04 or B1.05) when the edit dialog opens — double-click the card if you need to reopen it.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => (await holdingCount(ctx, "CYB-T", "Network Security")) === 0,
      hint: "Drag the chip onto Monday 13:00. Then double-click it → set Lecturer and Room → Save.",
    },
    {
      id: "place-workcom",
      title: "2 of 3 — mind the lecturer",
      body:
        "Now place Workplace Communication. This one is about who takes it: watch your Staff pane as you choose.\n\nIf you pick someone already teaching at that hour you'll get a red double-booking — either move the class or choose a lecturer who is free. Cathy Freeman and Nelson Mandela are the likely candidates.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      // Placing the card is only half of it — this step is about who takes the
      // class, so it is not done until someone is on it and they are free.
      verify: async (ctx) => {
        const card = await placedCard(ctx, "CYB-T", "Workplace Communication");
        if (!card) return false;
        if (!(card.staff_name ?? "").trim()) return false;
        return cardIsClashFree(ctx, card.id);
      },
      hint: "Drop it on a clear CYB-T slot, then double-click it and set the Lecturer. If the card turns red, the lecturer is already teaching then — pick another, or move the class.",
    },
    {
      id: "place-incident",
      title: "3 of 3 — the double session",
      body:
        "Cyber Incident Response is one class delivered twice a week, so it has two chips. Place both.\n\nThe usual rule is to keep them on different days — the group sees the class twice across the week rather than twice in one sitting.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => (await holdingCount(ctx, "CYB-T", "Cyber Incident Response")) === 0,
      hint: "Place the first chip on, say, Tuesday morning and the second on Thursday morning. Each needs its own lecturer and room.",
    },
    {
      id: "clear-warnings",
      title: "Finish clean",
      body:
        "Last pass: open the Warnings tab and clear any hard warning naming a CYB-T class. Moving the card, changing its room, or swapping the lecturer will each do it, depending on what the warning says.\n\nThis step passes when CYB-T's holding area is empty and no hard warning mentions the group.",
      advance: "verify",
      target: "tab-warnings",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => {
        const pending = await holdingUnitNames(ctx, "CYB-T");
        if (pending.length > 0) return false;
        const report = await api.violationsReport(ctx.sessionId, "hard");
        return !report.rows.some((row) => (row.group ?? "").includes("CYB-T"));
      },
      hint: "Right-click a problem card → Move to alternate slot and let the app offer a placement that fits.",
    },
  ],
  recap: [
    "You took a group from an empty holding area to a clash-free week. 🎓",
    "That's the whole loop: data in, drag to schedule, watch the warnings, export out.",
    "Keeping a second view open is what makes clashes obvious before they happen.",
    "Reset or delete this sandbox from the ⋯ menu whenever you like.",
  ],
};

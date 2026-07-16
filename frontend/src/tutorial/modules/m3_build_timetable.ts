/** Module 3 — Build the timetable: place, move, edit, lock, undo. */
import type { TutorialModule } from "../types";
import {
  findCourseUnitBooking,
  holdingUnitNames,
  urlIntParam,
  urlTab,
  urlView,
} from "../verifyHelpers";

const THREAT = "Cyber Threat Intelligence — VU23223";

export const m3BuildTimetable: TutorialModule = {
  id: "m3_build_timetable",
  title: "Build the timetable",
  goal: "Schedule a class from the holding area, then move, edit, lock and undo.",
  startUrl: (ctx) =>
    `/timetable/${ctx.sessionId}?tab=timetable&view=course&course=${ctx.entities.courses["CYB-A"] ?? ""}`,
  steps: [
    {
      id: "goto-cyb-a",
      title: "Open CYB-A's course view",
      body:
        "On the Timetable tab, set the sidebar view to Courses and select CYB-A — the Cyber Security Group A cohort.",
      advance: "verify",
      target: "sidebar",
      watch: { url: true },
      verify: (ctx) =>
        urlTab(ctx) === "timetable" &&
        urlView(ctx) === "course" &&
        urlIntParam(ctx, "course") === ctx.entities.courses["CYB-A"],
    },
    {
      id: "place-class",
      title: "Schedule the waiting class",
      body:
        "CYB-A's holding area has one unscheduled class: Cyber Threat Intelligence. Drag its chip out of the holding area and drop it on Wednesday mid-morning (the cohort is free after its 11:00 finish).",
      advance: "verify",
      target: "holding-area",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => !(await holdingUnitNames(ctx, "CYB-A")).includes(THREAT),
      hint: "Press and drag the 'Cyber Threat Intelligence' chip from the holding strip onto the Wednesday column around 11:00, then release.",
    },
    {
      id: "move-class",
      title: "Move it",
      body:
        "Plans change. Drag the placecard you just made to Thursday instead — any free slot works.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => {
        const booking = await findCourseUnitBooking(ctx, "CYB-A", THREAT);
        return booking != null && booking.day === 3;
      },
      hint: "Drag the card itself (not the holding chip) across to the Thursday column. Thursday is clear for CYB-A after 11:00.",
    },
    {
      id: "set-room",
      title: "Give it a room",
      body:
        "Double-click the placecard to open its editor, set the room to B1.05 (Cyber Lab 2), and save.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => {
        const booking = await findCourseUnitBooking(ctx, "CYB-A", THREAT);
        return booking?.room_code === "B1.05";
      },
      hint: "Double-click the Cyber Threat Intelligence card, pick B1.05 in the Room dropdown, then Save changes. If B1.05 clashes at that time, move the card first.",
    },
    {
      id: "lock-time",
      title: "Lock the time",
      body:
        "Some bookings must never drift. Right-click the card and choose Lock time — locked cards can't be dragged until unlocked the same way.",
      advance: "verify",
      watch: { api: /\/bookings/ },
      verify: async (ctx) => {
        const booking = await findCourseUnitBooking(ctx, "CYB-A", THREAT);
        return booking?.lock_time === true;
      },
      hint: "Right-click the placecard → Lock time. A small padlock appears on the card.",
    },
    {
      id: "undo",
      title: "Undo it",
      body:
        "Every scheduling edit is undoable. Press ⌘Z (or click Undo in the toolbar) to remove the lock you just set. Redo (⌘⇧Z) brings changes back.",
      advance: "verify",
      target: "undo-button",
      watch: { api: /\/bookings\/restore/ },
      verify: async (ctx) => {
        const booking = await findCourseUnitBooking(ctx, "CYB-A", THREAT);
        return booking != null && booking.lock_time !== true;
      },
      hint: "Click the Undo button in the top toolbar (or press ⌘Z / Ctrl+Z).",
    },
    {
      id: "alternate-slots",
      title: "Let the app suggest a slot",
      body:
        "Stuck for a spot? Right-click any placecard and open Alternate slots — it lists clash-free day/time/room combinations for that class. Try it on any card if you're curious, then move on.",
      advance: "next",
    },
  ],
  recap: [
    "Drag from the holding area to schedule; drag cards to move them.",
    "Double-click a card to edit its room, lecturer, times and terms.",
    "Right-click for lock, colours, alternate slots and more — and ⌘Z undoes anything.",
  ],
};

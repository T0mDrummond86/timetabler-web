/** The standard cover email, ready to paste.
 *
 * The message goes to both lecturers, so the greeting names both: the closing
 * line asks the lecturer being covered to do something, which only reads
 * correctly if they are a recipient too.
 */

export type CoverEmailFacts = {
  /** ISO date of the session being covered. */
  date: string;
  dayLabel: string;
  timeLabel: string;
  groupName: string;
  unitName: string;
  roomCode: string;
  awayStaffName: string;
  coverStaffName: string;
};

/** "2026-08-07" -> "Friday 7 August 2026", falling back to the raw value. */
export function longDate(iso: string, dayLabel: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return dayLabel || iso;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (Number.isNaN(d.getTime())) return dayLabel || iso;
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/** The block of class details quoted in the middle of the email. */
export function coverDetailLines(f: CoverEmailFacts): string[] {
  return [
    `Date: ${longDate(f.date, f.dayLabel)}`,
    `Time: ${f.timeLabel}`,
    `Group: ${f.groupName}`,
    `Class: ${f.unitName}`,
    `Room: ${f.roomCode || "—"}`,
    `Lecturer being covered: ${f.awayStaffName}`,
    `Covering lecturer: ${f.coverStaffName}`,
  ];
}

export function buildCoverEmail(f: CoverEmailFacts): string {
  return [
    `Hi ${f.coverStaffName} and ${f.awayStaffName},`,
    "",
    "As discussed, details for the cover session are as follows:",
    "",
    ...coverDetailLines(f),
    "",
    `${f.awayStaffName}, please ensure ${f.coverStaffName} has access to the shell and provide a session plan.`,
    "",
    "Thanks",
  ].join("\n");
}

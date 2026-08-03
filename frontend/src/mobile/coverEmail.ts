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

function firstNameOf(full: string): string {
  return full.trim().split(/\s+/)[0] ?? full.trim();
}

/**
 * How to address the two of them: first names, since the note is between
 * colleagues — unless they share one, where first names alone would leave the
 * reader guessing which of them is being asked for the session plan. Both
 * revert together, so the message never mixes the two forms.
 */
export function displayNames(f: CoverEmailFacts): { cover: string; away: string } {
  const cover = firstNameOf(f.coverStaffName);
  const away = firstNameOf(f.awayStaffName);
  if (cover.toLocaleLowerCase() === away.toLocaleLowerCase()) {
    return { cover: f.coverStaffName.trim(), away: f.awayStaffName.trim() };
  }
  return { cover, away };
}

/** The block of class details quoted in the middle of the email. */
export function coverDetailLines(f: CoverEmailFacts): string[] {
  const who = displayNames(f);
  return [
    `Date: ${longDate(f.date, f.dayLabel)}`,
    `Time: ${f.timeLabel}`,
    `Group: ${f.groupName}`,
    `Class: ${f.unitName}`,
    `Room: ${f.roomCode || "—"}`,
    `Lecturer being covered: ${who.away}`,
    `Covering lecturer: ${who.cover}`,
  ];
}

export function buildCoverEmail(f: CoverEmailFacts): string {
  const who = displayNames(f);
  return [
    `Hi ${who.cover} and ${who.away},`,
    "",
    "As discussed, details for the cover session are as follows:",
    "",
    ...coverDetailLines(f),
    "",
    `${who.away}, please ensure ${who.cover} has access to the shell and provide a session plan.`,
    "",
    "Thanks",
  ].join("\n");
}

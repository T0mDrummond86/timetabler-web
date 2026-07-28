/** A lecturer's week sized to fit a phone in landscape with no scrolling.
 *
 * The grid only spans the hours actually taught, so a 9-to-3 week uses the
 * whole screen instead of leaving 08:00-22:00 of empty rows. */
import { useMemo, useState } from "react";
import { minutesToLabel, slotToMinutes, type LecturerWeek } from "./lecturerWeek";

type Card = LecturerWeek["bookings"][number];

export function MobileWeekGrid({ week }: { week: LecturerWeek }) {
  const [detail, setDetail] = useState<Card | null>(null);

  const { firstSlot, lastSlot } = useMemo(() => {
    if (!week.bookings.length) return { firstSlot: 0, lastSlot: week.numSlots };
    let lo = Number.POSITIVE_INFINITY;
    let hi = 0;
    for (const b of week.bookings) {
      lo = Math.min(lo, b.start_slot);
      hi = Math.max(hi, b.end_slot);
    }
    // A little air above and below so cards aren't flush to the frame.
    return {
      firstSlot: Math.max(0, lo - 1),
      lastSlot: Math.min(week.numSlots, hi + 1),
    };
  }, [week]);

  const span = Math.max(1, lastSlot - firstSlot);
  const byDay = useMemo(() => {
    const out: Card[][] = week.days.map(() => []);
    for (const b of week.bookings) if (out[b.day]) out[b.day].push(b);
    return out;
  }, [week]);

  // Hour lines only — half-hour ticks are noise at this size.
  const hourMarks = useMemo(() => {
    const marks: { slot: number; label: string }[] = [];
    for (let s = firstSlot; s < lastSlot; s++) {
      const mins = slotToMinutes(s, week.firstSlotTime, week.slotMinutes);
      if (mins % 60 === 0) marks.push({ slot: s, label: minutesToLabel(mins) });
    }
    return marks;
  }, [firstSlot, lastSlot, week]);

  if (!week.bookings.length) {
    return <p className="mv-empty">No classes timetabled for {week.name}.</p>;
  }

  return (
    <>
      <div className="mv-grid" style={{ ["--mv-span" as string]: String(span) }}>
        <div className="mv-times">
          {hourMarks.map((m) => (
            <span
              key={m.slot}
              className="mv-time"
              style={{ top: `${((m.slot - firstSlot) / span) * 100}%` }}
            >
              {m.label}
            </span>
          ))}
        </div>
        {week.days.map((day, i) => (
          <div key={day} className="mv-day">
            <div className="mv-day-head">{day.slice(0, 3)}</div>
            <div className="mv-day-body">
              {hourMarks.map((m) => (
                <span
                  key={m.slot}
                  className="mv-rule"
                  style={{ top: `${((m.slot - firstSlot) / span) * 100}%` }}
                  aria-hidden
                />
              ))}
              {byDay[i].map((b) => {
                const top = ((b.start_slot - firstSlot) / span) * 100;
                const height = ((b.end_slot - b.start_slot) / span) * 100;
                return (
                  <button
                    key={`${b.id}-${b.sessionName}`}
                    type="button"
                    className="mv-card"
                    style={{ top: `${top}%`, height: `${height}%` }}
                    onClick={() => setDetail(b)}
                    title="Tap for full detail"
                  >
                    <span className="mv-card-name">
                      {b.unit_name ?? b.course_code ?? "Class"}
                    </span>
                    <span className="mv-card-meta">
                      {minutesToLabel(
                        slotToMinutes(b.start_slot, week.firstSlotTime, week.slotMinutes),
                      )}
                      {b.room_code ? ` · ${b.room_code}` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {detail && (
        <div className="mv-sheet" role="dialog" onClick={() => setDetail(null)}>
          <div className="mv-sheet-card" onClick={(e) => e.stopPropagation()}>
            <h2>{detail.unit_name ?? detail.course_code ?? "Class"}</h2>
            <dl className="mv-sheet-list">
              <Row label="Group" value={detail.course_code} />
              <Row
                label="Time"
                value={`${week.days[detail.day]} ${minutesToLabel(
                  slotToMinutes(detail.start_slot, week.firstSlotTime, week.slotMinutes),
                )} – ${minutesToLabel(
                  slotToMinutes(detail.end_slot, week.firstSlotTime, week.slotMinutes),
                )}`}
              />
              <Row label="Room" value={detail.room_code} />
              <Row label="Lecturer" value={detail.staff_name} />
              <Row label="Units" value={detail.unit_component_codes} />
              <Row label="Timetable" value={detail.sessionName} />
            </dl>
            <button type="button" className="mv-sheet-close" onClick={() => setDetail(null)}>
              Close
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function Row({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

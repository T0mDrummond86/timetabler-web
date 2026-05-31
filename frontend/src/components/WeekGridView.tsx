import { BookingCard, TimetableGrid } from "../types";

const SLOT_HEIGHT = 22;
const LANE_GAP = 2;
const LANE_PAD = 2;

function slotLabel(firstSlotTime: string, slotMinutes: number, slot: number): string {
  const [h, m] = firstSlotTime.split(":").map(Number);
  const total = h * 60 + m + slot * slotMinutes;
  const hh = Math.floor(total / 60);
  const mm = total % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

function cardTitle(b: BookingCard): string {
  const parts: string[] = [];
  if (b.external_id) parts.push(`[${b.external_id}]`);
  if (b.unit_name) parts.push(b.unit_name);
  return parts.join(" ") || `Booking #${b.id}`;
}

function cardSubtitle(b: BookingCard): string {
  const bits: string[] = [];
  if (b.staff_name) bits.push(b.staff_name);
  if (b.room_code) bits.push(b.room_code);
  return bits.join(" · ");
}

type Props = {
  grid: TimetableGrid;
};

export function WeekGridView({ grid }: Props) {
  const gridHeight = grid.num_slots * SLOT_HEIGHT;

  const byDay: BookingCard[][] = grid.days.map((_, day) =>
    grid.bookings.filter((b) => b.day === day),
  );

  return (
    <div className="week-grid-wrap">
      <div
        className="week-grid"
        style={{ gridTemplateColumns: `56px repeat(${grid.days.length}, minmax(140px, 1fr))` }}
      >
        <div className="time-axis" style={{ height: gridHeight }}>
          {Array.from({ length: grid.num_slots }, (_, s) => (
            <div key={s} className="time-slot" style={{ height: SLOT_HEIGHT }}>
              {s % 2 === 0 ? slotLabel(grid.first_slot_time, grid.slot_minutes, s) : ""}
            </div>
          ))}
        </div>

        {grid.days.map((dayName, dayIndex) => (
          <div key={dayName} className="day-column">
            <div className="day-header">{dayName}</div>
            <div className="day-body" style={{ height: gridHeight }}>
              {Array.from({ length: grid.num_slots + 1 }, (_, s) => (
                <div
                  key={s}
                  className="slot-line"
                  style={{ top: s * SLOT_HEIGHT }}
                />
              ))}
              {byDay[dayIndex].map((b) => {
                const top = b.start_slot * SLOT_HEIGHT;
                const height = (b.end_slot - b.start_slot) * SLOT_HEIGHT - 2;
                const widthPct = 100 / b.lane_depth;
                const leftPct = b.lane * widthPct;
                return (
                  <div
                    key={b.id}
                    className={`booking-card${b.is_hard ? " hard" : ""}${b.is_soft ? " soft" : ""}`}
                    style={{
                      top,
                      height: Math.max(height, 18),
                      left: `calc(${leftPct}% + ${LANE_PAD}px)`,
                      width: `calc(${widthPct}% - ${LANE_PAD * 2 + LANE_GAP}px)`,
                      backgroundColor: b.fill_colour,
                      borderLeftColor: b.border_colour,
                    }}
                    title={
                      b.violations.length
                        ? b.violations.map((v) => v.message).join("\n")
                        : undefined
                    }
                  >
                    <div className="card-title">{cardTitle(b)}</div>
                    {cardSubtitle(b) && (
                      <div className="card-sub">{cardSubtitle(b)}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export { SLOT_HEIGHT };

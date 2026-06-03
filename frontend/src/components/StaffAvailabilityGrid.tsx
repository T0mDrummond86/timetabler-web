import { useEffect, useState } from "react";
import { slotToTimeLabel } from "../lib/timeUtils";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const NUM_SLOTS = 28;

type Props = {
  blocked: Set<string>;
  onChange: (blocked: Set<string>) => void;
  disabled?: boolean;
};

function key(day: number, slot: number) {
  return `${day}:${slot}`;
}

export function StaffAvailabilityGrid({ blocked, onChange, disabled }: Props) {
  const [dragging, setDragging] = useState<"block" | "clear" | null>(null);

  useEffect(() => {
    function onUp() {
      setDragging(null);
    }
    window.addEventListener("mouseup", onUp);
    return () => window.removeEventListener("mouseup", onUp);
  }, []);

  function toggle(day: number, slot: number, mode: "block" | "clear") {
    const next = new Set(blocked);
    const k = key(day, slot);
    if (mode === "block") next.add(k);
    else next.delete(k);
    onChange(next);
  }

  function paint(day: number, slot: number) {
    if (!dragging || disabled) return;
    toggle(day, slot, dragging);
  }

  return (
    <div className="staff-availability-grid-wrap">
      <p className="muted entity-hint">
        Checked slots are unavailable. Drag to paint blocked times (matches desktop Staff tab).
      </p>
      <div className="staff-availability-grid">
        <div className="avail-corner" />
        {DAYS.map((d) => (
          <div key={d} className="avail-day-header">
            {d}
          </div>
        ))}
        {Array.from({ length: NUM_SLOTS }, (_, slot) => (
          <div key={slot} className="avail-row">
            <div className={`avail-time${slot % 2 === 0 ? " hour" : ""}`}>
              {slot % 2 === 0 ? slotToTimeLabel(slot) : ""}
            </div>
            {DAYS.map((_, day) => {
              const k = key(day, slot);
              const isBlocked = blocked.has(k);
              return (
                <label key={k} className={`avail-cell${isBlocked ? " blocked" : ""}`}>
                  <input
                    type="checkbox"
                    checked={isBlocked}
                    disabled={disabled}
                    onChange={(e) => toggle(day, slot, e.target.checked ? "block" : "clear")}
                    onMouseDown={(e) => {
                      if (disabled) return;
                      e.preventDefault();
                      const mode = isBlocked ? "clear" : "block";
                      setDragging(mode);
                      toggle(day, slot, mode);
                    }}
                    onMouseEnter={() => paint(day, slot)}
                  />
                </label>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export function blockedSetFromApi(rows: { day: number; slot: number }[]): Set<string> {
  return new Set(rows.map((r) => key(r.day, r.slot)));
}

export function blockedApiFromSet(blocked: Set<string>): { day: number; slot: number }[] {
  return [...blocked].map((k) => {
    const [day, slot] = k.split(":").map(Number);
    return { day, slot };
  });
}

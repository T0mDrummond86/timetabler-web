/** "Free right now" — who you could grab at this moment, split by whether the
 *  timetable suggests they are on site today. */
import { useCallback, useEffect, useState } from "react";
import { loadFreeNow, type FreeNowResult, type FreeRow } from "./freeNow";

type Props = {
  sessionIds: number[];
  lecturerNames: string[];
  onError?: (message: string) => void;
};

/** Re-check on the half hour, since that is when the grid can change. */
const TICK_MS = 60_000;

export function FreeNowView({ sessionIds, lecturerNames, onError }: Props) {
  const [result, setResult] = useState<FreeNowResult | null>(null);
  const [loading, setLoading] = useState(true);

  const key = sessionIds.join(",");

  const load = useCallback(async () => {
    if (!sessionIds.length || !lecturerNames.length) {
      setLoading(false);
      return;
    }
    try {
      setResult(await loadFreeNow(sessionIds, lecturerNames));
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Could not work out who is free");
    } finally {
      setLoading(false);
    }
    // key stands in for sessionIds so a new array identity alone doesn't refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, lecturerNames.length, onError]);

  useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), TICK_MS);
    return () => window.clearInterval(t);
  }, [load]);

  if (loading) return <p className="mv-empty">Working out who's free…</p>;
  if (!result) return <p className="mv-empty">Choose at least one timetable first.</p>;

  if (result.dayIndex < 0) {
    return (
      <div className="fn-wrap">
        <p className="mv-empty">
          It's {result.dayLabel} — timetables only cover Monday to Friday, so everyone is off
          campus.
        </p>
      </div>
    );
  }

  const onCampus = result.rows.filter((r) => r.state === "free_on_campus");
  const offCampus = result.rows.filter((r) => r.state === "free_off_campus");
  const busy = result.rows.filter((r) => r.state === "busy");

  return (
    <div className="fn-wrap">
      <div className="fn-clock">
        <strong>{result.dayLabel}</strong> {result.clockLabel}
        {result.offGrid && (
          <span className="muted">
            {" "}
            · outside timetabled hours, so nobody is in class
          </span>
        )}
      </div>

      <div className="fn-columns">
        <FreeGroup
          title="Free · on campus"
          hint="Teaching at some point today, but not right now."
          tone="on"
          rows={onCampus}
        />
        <FreeGroup
          title="Free · off campus"
          hint="Nothing scheduled today."
          tone="off"
          rows={offCampus}
        />
        <FreeGroup
          title="In class"
          hint="Busy right now."
          tone="busy"
          rows={busy}
        />
      </div>
    </div>
  );
}

function FreeGroup({
  title,
  hint,
  tone,
  rows,
}: {
  title: string;
  hint: string;
  tone: "on" | "off" | "busy";
  rows: FreeRow[];
}) {
  return (
    <section className={`fn-group fn-group--${tone}`}>
      <h2 className="fn-group-head">
        {title}
        <span className="fn-count">{rows.length}</span>
      </h2>
      <p className="fn-hint muted">{hint}</p>
      {!rows.length && <p className="fn-none muted">Nobody</p>}
      <ul className="fn-list">
        {rows.map((r) => (
          <li key={r.name} className="fn-row">
            <span className="fn-name">{r.name}</span>
            {r.state === "busy" && r.current && (
              <span className="fn-meta muted">
                {r.current.label}
                {r.current.room ? ` · ${r.current.room}` : ""} · until {r.current.until}
              </span>
            )}
            {r.state === "free_on_campus" && (
              <span className="fn-meta muted">
                {r.next
                  ? `free until ${r.next.from} · then ${r.next.label}${
                      r.next.room ? ` · ${r.next.room}` : ""
                    }`
                  : `done for the day · ${r.countToday} class${r.countToday === 1 ? "" : "es"} today`}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

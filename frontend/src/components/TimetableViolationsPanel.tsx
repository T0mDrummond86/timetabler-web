import type { Violation } from "../types";

type Props = {
  violations: Violation[];
  onViewAll?: () => void;
};

export function TimetableViolationsPanel({ violations, onViewAll }: Props) {
  if (!violations.length) return null;

  const hardCount = violations.filter((v) => v.severity === "hard").length;
  const softCount = violations.length - hardCount;

  return (
    <details className="panel violations-panel violations-panel--collapsible">
      <summary className="violations-panel-summary">
        <span className="violations-panel-summary-text">
          <strong>{violations.length}</strong> scheduling warning
          {violations.length !== 1 ? "s" : ""} on this view
          {hardCount > 0 && softCount > 0 && (
            <span className="violations-panel-summary-meta muted">
              {" "}
              ({hardCount} hard, {softCount} soft)
            </span>
          )}
        </span>
        <span className="violations-panel-chevron" aria-hidden>
          ▸
        </span>
      </summary>
      <div className="violations-panel-body">
        <ul className="violations-panel-list">
          {violations.map((v, index) => (
            <li
              key={`${v.code}-${v.booking_ids?.join("-") ?? index}`}
              className={v.severity === "hard" ? "hard" : "soft"}
            >
              <span className={`violations-panel-severity violations-panel-severity--${v.severity}`}>
                {v.severity}
              </span>
              {v.message}
            </li>
          ))}
        </ul>
        {onViewAll && (
          <div className="violations-panel-footer">
            <button type="button" className="btn-secondary btn-xs" onClick={onViewAll}>
              View all warnings
            </button>
          </div>
        )}
      </div>
    </details>
  );
}

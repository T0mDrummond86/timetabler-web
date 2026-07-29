/** View-scoped warning count as a topbar chip.
 *
 * Replaces a full-width strip below the grid that spent ~50px repeating what
 * the Warnings tab badge already implies. The list is still one click away. */
import { useDropdown } from "../hooks/useDropdown";
import type { Violation } from "../types";

type Props = {
  violations: Violation[];
  onViewAll?: () => void;
};

export function ViolationsChip({ violations, onViewAll }: Props) {
  const menu = useDropdown();
  if (!violations.length) return null;

  const hardCount = violations.filter((v) => v.severity === "hard").length;
  const softCount = violations.length - hardCount;

  return (
    <span className="tt-dropdown-wrap" ref={menu.wrapRef}>
      <button
        type="button"
        className={`violations-chip${hardCount ? " violations-chip--hard" : ""}`}
        onClick={menu.toggle}
        aria-expanded={menu.open}
        aria-haspopup="menu"
        title={`${violations.length} scheduling warning${
          violations.length === 1 ? "" : "s"
        } on this view${
          hardCount && softCount ? ` (${hardCount} hard, ${softCount} soft)` : ""
        }`}
      >
        <span aria-hidden>⚠</span>
        {violations.length}
      </button>
      {menu.open && (
        <div className="tt-dropdown-menu violations-chip-menu" role="menu">
          <span className="ctx-label">
            On this view
            {hardCount && softCount ? ` · ${hardCount} hard, ${softCount} soft` : ""}
          </span>
          <ul className="violations-panel-list">
            {violations.map((v, index) => (
              <li
                key={`${v.code}-${v.booking_ids?.join("-") ?? index}`}
                className={v.severity === "hard" ? "hard" : "soft"}
              >
                <span
                  className={`violations-panel-severity violations-panel-severity--${v.severity}`}
                >
                  {v.severity}
                </span>
                {v.message}
              </li>
            ))}
          </ul>
          {onViewAll && (
            <div className="violations-panel-footer">
              <button
                type="button"
                className="btn-secondary btn-xs"
                onClick={() => {
                  menu.close();
                  onViewAll();
                }}
              >
                View all warnings
              </button>
            </div>
          )}
        </div>
      )}
    </span>
  );
}

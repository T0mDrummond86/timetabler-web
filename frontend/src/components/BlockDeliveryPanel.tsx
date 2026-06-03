import { useState } from "react";
import type { BlockDeliveryPanel as BlockPanel } from "../types";

type Props = {
  panel: BlockPanel | null;
  loading?: boolean;
  onCourseChange: (courseId: number) => void;
  onBlockWeekChange: (index: number) => void;
  onStartWeekChange?: (week: number) => void;
  onBlockLengthChange?: (weeks: number) => void;
  onDuplicateGroup?: (newCode: string) => void;
  onDeleteGroup?: () => void;
  suggestedCode?: string | null;
  /** Compact layout for left sidebar (split view). */
  embedded?: boolean;
};

export function BlockDeliveryPanel({
  panel,
  loading,
  onCourseChange,
  onBlockWeekChange,
  onStartWeekChange,
  onBlockLengthChange,
  onDuplicateGroup,
  onDeleteGroup,
  suggestedCode,
  embedded = false,
}: Props) {
  const [dupCode, setDupCode] = useState("");

  if (loading) {
    return (
      <div className={`tt-sidebar-section${embedded ? " block-panel-embedded" : ""}`}>
        <div className="muted">Loading block delivery…</div>
      </div>
    );
  }
  if (!panel) return null;

  const weekCount = Math.max(1, panel.block_week_count);
  const canAdmin = Boolean(panel.selected_course_id && panel.groups.length);

  if (embedded) {
    return (
      <div className="tt-sidebar-section block-panel-embedded">
        <span className="tt-sidebar-label">Block delivery</span>
        <p className="block-panel-embedded-title">{panel.qualification_name}</p>
        <ul className="tt-sidebar-pick-list" role="listbox" aria-label="Block groups">
          {panel.groups.map((g) => (
            <li key={g.id}>
              <button
                type="button"
                role="option"
                aria-selected={panel.selected_course_id === g.id}
                className={`tt-entity-item${panel.selected_course_id === g.id ? " active" : ""}`}
                onClick={() => onCourseChange(g.id)}
              >
                {g.code}
              </button>
            </li>
          ))}
        </ul>
        {canAdmin && onBlockLengthChange && (
          <label className="block-panel-embedded-field">
            Block length
            <input
              type="number"
              className="field-input"
              min={1}
              max={3}
              value={panel.block_week_count}
              onChange={(e) => onBlockLengthChange(Number(e.target.value))}
            />
          </label>
        )}
        {canAdmin && onStartWeekChange && (
          <label className="block-panel-embedded-field">
            Starts semester week
            <input
              type="number"
              className="field-input"
              min={1}
              max={20}
              value={panel.block_start_semester_week}
              onChange={(e) => onStartWeekChange(Number(e.target.value))}
            />
          </label>
        )}
        <ul className="tt-sidebar-pick-list block-week-pick-list" role="listbox" aria-label="Block week">
          {Array.from({ length: weekCount }, (_, i) => i + 1).map((idx) => (
            <li key={idx}>
              <button
                type="button"
                role="option"
                aria-selected={panel.block_week_index === idx}
                className={`tt-entity-item${panel.block_week_index === idx ? " active" : ""}`}
                onClick={() => onBlockWeekChange(idx)}
              >
                Week {idx}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <section className="panel block-panel">
      <div className="panel-header">
        <h2>Block delivery — {panel.qualification_name}</h2>
      </div>
      <div className="panel-body">
        <div className="block-panel-row block-panel-actions">
          <span className="tt-sidebar-label">Groups</span>
          <div className="block-group-list">
            {panel.groups.map((g) => (
              <button
                key={g.id}
                type="button"
                className={`btn-chip${panel.selected_course_id === g.id ? " active" : ""}`}
                onClick={() => onCourseChange(g.id)}
              >
                {g.code}
              </button>
            ))}
          </div>
          {canAdmin && onDuplicateGroup && (
            <>
              <input
                className="field-input block-dup-input"
                placeholder="New group code"
                value={dupCode || suggestedCode || ""}
                onChange={(e) => setDupCode(e.target.value)}
              />
              <button
                type="button"
                className="btn-secondary"
                onClick={() => onDuplicateGroup(dupCode || suggestedCode || "")}
              >
                Duplicate group
              </button>
            </>
          )}
          {canAdmin && onDeleteGroup && (
            <button type="button" className="btn-secondary btn-danger-text" onClick={onDeleteGroup}>
              Delete group
            </button>
          )}
        </div>

        <div className="block-panel-row">
          <span className="muted">{panel.summary}</span>
        </div>

        {canAdmin && onBlockLengthChange && (
          <div className="block-panel-row">
            <label>
              Block length (weeks)
              <input
                type="number"
                className="field-input block-spin"
                min={1}
                max={3}
                value={panel.block_week_count}
                onChange={(e) => onBlockLengthChange(Number(e.target.value))}
              />
            </label>
            {onStartWeekChange && (
              <label>
                Starts semester week
                <input
                  type="number"
                  className="field-input block-spin"
                  min={1}
                  max={20}
                  value={panel.block_start_semester_week}
                  onChange={(e) => onStartWeekChange(Number(e.target.value))}
                />
              </label>
            )}
          </div>
        )}

        <div className="block-panel-row block-week-buttons">
          {Array.from({ length: weekCount }, (_, i) => i + 1).map((idx) => (
            <button
              key={idx}
              type="button"
              className={`btn-secondary${panel.block_week_index === idx ? " active" : ""}`}
              onClick={() => onBlockWeekChange(idx)}
            >
              Week {idx}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

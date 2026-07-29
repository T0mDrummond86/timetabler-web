import type { ReactNode } from "react";
import type { TimetableMode, ViewKind } from "../viewKinds";
import { VIEW_KINDS_BY_MODE } from "../viewKinds";
import type { TimetableEntity } from "../types";

const READ_ONLY = "Read-only access — you cannot make changes to this session";

type Props = {
  mode: TimetableMode;
  onModeChange: (mode: TimetableMode) => void;
  viewKind: ViewKind;
  onViewKindChange: (kind: ViewKind) => void;
  entities: TimetableEntity[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  filter: string;
  onFilterChange: (value: string) => void;
  reorderable?: boolean;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  courseAdmin?: boolean;
  onCourseAdd?: () => void;
  onCourseDuplicate?: () => void;
  /** False when the user only has read access. */
  canEdit?: boolean;
  /** False when the session is pinned to a single mode — hides the selector. */
  showModeSelector?: boolean;
  onCourseDelete?: () => void;
  onCourseToggleLock?: () => void;
  courseLocked?: boolean;
  staffAdmin?: boolean;
  onStaffToggleLock?: () => void;
  staffLocked?: boolean;
  /** Shown at top of sidebar (e.g. split active-pane hint). */
  header?: ReactNode;
  /** Inserted after view controls, before SELECT (semester week, block delivery). */
  viewExtras?: ReactNode;
  /** Collapsed to a rail, handing the grid the sidebar's width. */
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
};

const MODES: { value: TimetableMode; label: string }[] = [
  { value: "regular", label: "Regular" },
  { value: "block", label: "Block" },
];

function SidebarSelect<T extends string>({
  id,
  label,
  options,
  value,
  onChange,
}: {
  id: string;
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <label className="tt-sidebar-field" htmlFor={id}>
      <span className="tt-sidebar-label">{label}</span>
      <select
        id={id}
        className="field-input tt-sidebar-select"
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function TimetableSidebar({
  mode,
  onModeChange,
  viewKind,
  onViewKindChange,
  entities,
  selectedId,
  onSelect,
  filter,
  onFilterChange,
  reorderable = false,
  onMoveUp,
  onMoveDown,
  courseAdmin = false,
  onCourseAdd,
  onCourseDuplicate,
  canEdit = true,
  showModeSelector = true,
  onCourseDelete,
  onCourseToggleLock,
  courseLocked = false,
  staffAdmin = false,
  onStaffToggleLock,
  staffLocked = false,
  header,
  viewExtras,
  collapsed = false,
  onToggleCollapsed,
}: Props) {
  const filtered = entities.filter((e) =>
    e.label.toLowerCase().includes(filter.toLowerCase()),
  );
  const viewOptions = VIEW_KINDS_BY_MODE[mode];

  const selectedLabel = entities.find((e) => e.id === selectedId)?.label ?? null;

  if (collapsed) {
    return (
      <aside className="tt-sidebar tt-sidebar--rail" data-tutorial-id="sidebar">
        <button
          type="button"
          className="tt-rail-toggle"
          onClick={onToggleCollapsed}
          aria-expanded={false}
          title="Show the view and selection controls"
        >
          ›
        </button>
        {selectedLabel && (
          <span className="tt-rail-label" title={selectedLabel}>
            {selectedLabel}
          </span>
        )}
      </aside>
    );
  }

  return (
    <aside className="tt-sidebar" data-tutorial-id="sidebar">
      {onToggleCollapsed && (
        <button
          type="button"
          className="tt-rail-toggle tt-rail-toggle--open"
          onClick={onToggleCollapsed}
          aria-expanded
          title="Collapse this panel and give the grid the space"
        >
          ‹
        </button>
      )}
      {header}

      <div className="tt-sidebar-section tt-sidebar-mode-view">
        {showModeSelector && (
          <SidebarSelect
            id="tt-sidebar-mode"
            label="Mode"
            options={MODES}
            value={mode}
            onChange={onModeChange}
          />
        )}
        <SidebarSelect
          id="tt-sidebar-view"
          label="View"
          options={viewOptions}
          value={viewKind}
          onChange={onViewKindChange}
        />
      </div>

      {viewExtras}

      {courseAdmin && (
        <div className="tt-sidebar-section tt-sidebar-course-admin">
          <span className="tt-sidebar-label">Course</span>
          <div className="tt-course-admin-btns">
            <button type="button" className="btn-secondary btn-xs" onClick={onCourseAdd} disabled={!canEdit} title={canEdit ? undefined : READ_ONLY}>
              Add
            </button>
            <button type="button" className="btn-secondary btn-xs" onClick={onCourseDuplicate} disabled={!canEdit} title={canEdit ? undefined : READ_ONLY}>
              Duplicate
            </button>
            <button type="button" className="btn-secondary btn-xs" onClick={onCourseDelete} disabled={!canEdit} title={canEdit ? undefined : READ_ONLY}>
              Delete
            </button>
            <button type="button" className="btn-secondary btn-xs" onClick={onCourseToggleLock} disabled={!canEdit} title={canEdit ? undefined : READ_ONLY}>
              {courseLocked ? "Unlock" : "Lock"}
            </button>
          </div>
        </div>
      )}

      {staffAdmin && onStaffToggleLock && (
        <div className="tt-sidebar-section">
          <span className="tt-sidebar-label">Staff</span>
          <div className="tt-sidebar-admin">
            <button type="button" className="btn-secondary btn-xs" onClick={onStaffToggleLock}>
              {staffLocked ? "Unlock lecturer" : "Lock lecturer"}
            </button>
          </div>
        </div>
      )}

      <div className="tt-sidebar-section tt-sidebar-grow">
        <div className="tt-sidebar-list-header">
          <span className="tt-sidebar-label">Select</span>
          {reorderable && onMoveUp && onMoveDown && (
            <span className="tt-reorder-btns">
              <button type="button" className="btn-secondary btn-xs" onClick={onMoveUp} title="Move up">
                ↑
              </button>
              <button type="button" className="btn-secondary btn-xs" onClick={onMoveDown} title="Move down">
                ↓
              </button>
            </span>
          )}
        </div>
        {viewKind !== "block_overview" && (
          <input
            className="field-input tt-sidebar-filter"
            placeholder="Filter list…"
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
          />
        )}
        <ul className="tt-entity-list" role="listbox" aria-label="Entities">
          {filtered.map((row) => (
            <li key={`${row.entity_type}-${row.id}`}>
              <button
                type="button"
                role="option"
                aria-selected={selectedId === row.id}
                className={`tt-entity-item${selectedId === row.id ? " active" : ""}`}
                onClick={() => onSelect(row.id)}
              >
                {row.label}
              </button>
            </li>
          ))}
          {!filtered.length && viewKind === "room" && (
            <li className="tt-entity-empty">All rooms are shown as columns.</li>
          )}
          {!filtered.length && viewKind === "block_overview" && (
            <li className="tt-entity-empty">Overview shows all block groups.</li>
          )}
          {!filtered.length && viewKind !== "room" && viewKind !== "block_overview" && (
            <li className="tt-entity-empty">No matches</li>
          )}
        </ul>
      </div>
    </aside>
  );
}

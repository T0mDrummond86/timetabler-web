import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { api, type Course } from "../api";

type Props = {
  sessionId: number;
  courseId: number;
  value: string;
  editable?: boolean;
  compact?: boolean;
  suffix?: ReactNode;
  onRenamed: (course: Course) => void;
  onError?: (message: string) => void;
};

export function EditableGroupTitle({
  sessionId,
  courseId,
  value,
  editable = true,
  compact = false,
  suffix,
  onRenamed,
  onError,
}: Props) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const cancel = useCallback(() => {
    setDraft(value);
    setEditing(false);
  }, [value]);

  const save = useCallback(async () => {
    const next = draft.trim();
    if (!next) {
      onError?.("Group name cannot be empty");
      return;
    }
    if (next === value.trim()) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const updated = await api.patchCourse(sessionId, courseId, { code: next });
      onRenamed(updated);
      setEditing(false);
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setSaving(false);
    }
  }, [courseId, draft, onError, onRenamed, sessionId, value]);

  const Tag = compact ? "span" : "h1";
  const className = compact ? "split-pane-title editable-group-title" : "page-title editable-group-title";

  if (!editable) {
    return (
      <Tag className={className}>
        {value}
        {suffix}
      </Tag>
    );
  }

  if (editing) {
    return (
      <Tag className={className}>
        <label htmlFor={inputId} className="visually-hidden">
          Group name
        </label>
        <input
          id={inputId}
          ref={inputRef}
          className="editable-group-title-input"
          value={draft}
          disabled={saving}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void save();
            }
            if (e.key === "Escape") {
              e.preventDefault();
              cancel();
            }
          }}
          onBlur={() => {
            void save();
          }}
          aria-busy={saving}
        />
        {suffix}
      </Tag>
    );
  }

  return (
    <Tag className={className}>
      <button
        type="button"
        className="editable-group-title-btn"
        onClick={() => setEditing(true)}
        title="Click to rename this group"
      >
        <span className="editable-group-title-text">{value}</span>
        <span className="editable-group-title-hint" aria-hidden>
          ✎
        </span>
      </button>
      {suffix}
    </Tag>
  );
}

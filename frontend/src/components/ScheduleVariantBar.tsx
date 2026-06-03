import type { ScheduleVariant } from "../types";

type Props = {
  variants: ScheduleVariant[];
  selectedPreviewWeek: number | null;
  onSelect: (previewWeek: number | null) => void;
};

export function ScheduleVariantBar({ variants, selectedPreviewWeek, onSelect }: Props) {
  if (!variants.length) return null;

  return (
    <div className="schedule-variant-bar">
      <span className="tt-sidebar-label">Schedule</span>
      <div className="schedule-variant-buttons">
        <button
          type="button"
          className={`btn-chip${selectedPreviewWeek == null ? " active" : ""}`}
          onClick={() => onSelect(null)}
          title="Show the main timetable for this group"
        >
          Standard
        </button>
        {variants.map((v) => (
          <button
            key={v.preview_week}
            type="button"
            className={`btn-chip${selectedPreviewWeek === v.preview_week ? " active" : ""}`}
            onClick={() => onSelect(v.preview_week)}
            title={`Show timetable for ${v.label}`}
          >
            {v.label}
          </button>
        ))}
      </div>
    </div>
  );
}

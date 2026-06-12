import type { ViewKind } from "./viewKinds";

export type Violation = {
  severity: string;
  code: string;
  message: string;
  booking_ids?: number[];
};

export type TimetableView = ViewKind;

/** API may still return legacy grid views not offered in the UI. */
export type TimetableGridView = TimetableView | "co_teach";

export type BookingCard = {
  id: number;
  course_id: number | null;
  day: number;
  column: number | null;
  start_slot: number;
  end_slot: number;
  lane: number;
  lane_depth: number;
  layout_left_pct?: number;
  layout_width_pct?: number;
  unit_name: string | null;
  course_code: string | null;
  staff_name: string | null;
  room_code: string | null;
  room_id: number | null;
  notes: string | null;
  external_id: string | null;
  colour_key: string;
  fill_colour: string;
  border_colour: string;
  is_hard: boolean;
  is_soft: boolean;
  lock_time?: boolean;
  lock_staff?: boolean;
  in_term_1?: boolean;
  in_term_2?: boolean;
  unit_id?: number | null;
  unit_screen_fill_colour?: string | null;
  session_part?: number;
  sfs_co_teacher_staff_id?: number | null;
  sfs_co_teacher_name?: string | null;
  sfs_co_teacher_in_term_1?: boolean;
  sfs_co_teacher_in_term_2?: boolean;
  online_student_count?: number | null;
  room_is_online?: boolean;
  violations: Violation[];
};

export type ScheduleVariant = {
  label: string;
  preview_week: number;
};

export type TimetableGrid = {
  timetable_session_id: number;
  view: TimetableGridView;
  entity_id: number;
  entity_label: string;
  course_id: number | null;
  course_code: string | null;
  week_id: number;
  week_label: string;
  column_kind: "day" | "room" | "staff";
  focus_day: number | null;
  columns: string[];
  days: string[];
  num_slots: number;
  slot_minutes: number;
  first_slot_time: string;
  bookings: BookingCard[];
  violations: Violation[];
  semester_week?: number | null;
  block_week_index?: number | null;
  readonly?: boolean;
  schedule_variants?: ScheduleVariant[];
  preview_semester_week?: number | null;
  unavailable_slots?: Record<string, number[]> | null;
  linked_session_busy_slots?: Record<string, number[]> | null;
  linked_session_busy_label?: string | null;
  staff_hours?: number | null;
};

export type GlobalClassCustodians = {
  rows: {
    unit_id: number;
    unit_name: string;
    qualifications: string;
    lecturers: string;
    custodian: string;
    session_names: string[];
    session_count?: number;
  }[];
  summary: string;
};

export type TimetableEntity = {
  id: number;
  label: string;
  entity_type: string;
};

export type SemesterWeekCell = {
  week: number;
  active: boolean;
  applicable: boolean;
  booking_id: number;
};

export type SemesterScheduleRow = {
  primary_booking_id: number;
  label: string;
  has_variants: boolean;
  weeks: SemesterWeekCell[];
};

export type CourseSemesterSchedule = {
  course_id: number;
  course_code: string;
  selected_semester_week: number;
  semester_weeks: number;
  rows: SemesterScheduleRow[];
};

export type BlockDeliveryPanel = {
  qualification_id: number;
  qualification_name: string;
  groups: { id: number; code: string }[];
  selected_course_id: number | null;
  block_week_count: number;
  block_start_semester_week: number;
  block_week_index: number;
  summary: string;
};

export type BlockOverviewRow = {
  course_id: number;
  label: string;
  tooltip: string;
  calendar_weeks: number[];
};

export type BlockOverview = {
  rows: BlockOverviewRow[];
  semester_weeks: number;
};

export type BlockWeekUsageCell = {
  status: string;
  label: string;
  tooltip: string;
};

export type BlockWeekUsage = {
  title: string;
  subtitle: string;
  rooms: string[];
  days: string[];
  cells: BlockWeekUsageCell[][];
};

export type BookingChange = {
  description: string;
  before: Record<string, Record<string, unknown> | null>;
  after: Record<string, Record<string, unknown> | null>;
};

export type BookingMutation = {
  grid: TimetableGrid;
  change: BookingChange;
};

export type HoldingClass = {
  course_id: number;
  unit_id: number;
  unit_name: string | null;
  duration_slots: number;
  session_part: number;
};

export type ImportReport = {
  qualifications: number;
  courses: number;
  staff: number;
  rooms: number;
  bookings: number;
  source?: string;
};

export type ChangeLogRow = {
  when: string | null;
  action: "change" | "undo" | "redo" | "net" | string;
  booking_id: number | null;
  entry_id: number | null;
  note: string;
  row: {
    id?: string;
    group?: string;
    class?: string;
    lecturer_change?: string;
    time_change?: string;
    day_change?: string;
    room_change?: string;
    delete?: string;
  };
};

export type ChangeLogList = {
  mode: "full" | "resolved";
  rows: ChangeLogRow[];
};

export type ClashCheckSetting = {
  code: string;
  label: string;
  description: string;
  category: string;
  severity: "hard" | "soft";
  enabled: boolean;
};

export type ViolationRow = Record<string, string> & {
  booking_ids?: number[];
};

export type ViolationsReport = {
  summary: string;
  headers: string[];
  rows: ViolationRow[];
};

export type AlternatePlacementOption = {
  day: number;
  start_slot: number;
  end_slot: number;
  time_label: string;
  room_id: number | null;
  room_code: string;
  staff_id: number | null;
  is_current: boolean;
};

export type AlternateSlots = {
  days: {
    day: number;
    day_label: string;
    is_current_day: boolean;
    slots: {
      start_slot: number;
      time_label: string;
      options: AlternatePlacementOption[];
    }[];
  }[];
  available_rooms: { room_id: number; room_code: string; is_current: boolean }[];
};

export type ClassCustodians = {
  summary: string;
  rows: {
    unit_id: number;
    unit_name: string;
    qualifications: string;
    lecturers: string;
    custodian: string;
    custodian_deliveries: number;
    unassigned_deliveries: number;
  }[];
};

export type StaffAvailability = {
  blocked: { day: number; slot: number }[];
};

export type ResourceUsage = {
  kind: string;
  resources: string[];
  resource_ids: number[];
  resource_tooltips: string[];
  days: string[];
  num_slots: number;
  cells: {
    booking_id: number | null;
    label: string;
    fill_colour: string;
    status: string;
    tooltip: string;
    row_span: number;
  }[][][];
  summary: string;
  course_id?: number;
};

export type StaffHoursRow = {
  id: number;
  name: string;
  cost_centre: string | null;
  fte: number | null;
  lecturing_hours: number | null;
  in_class_timetabled_hours: number | null;
  session_schedule_avg: string | null;
  variance: number | null;
  variance_category: string;
  bulk_online_detail: string | null;
  bulk_online_hours_avg: number | null;
  development_project_hours: number | null;
  development_project_description: string | null;
  tae_hours: number | null;
  supervision_hours: number | null;
  total_hours: number;
  non_teaching_day: number | null;
  preferences_first: string;
  preferences_second: string;
  preferences_third: string;
};

export type StaffDetail = {
  id: number;
  name: string;
  cost_centre: string | null;
  fte: number | null;
  max_hours_per_week: number | null;
  non_teaching_day: number | null;
  ot_hours: number | null;
  development_project_hours: number | null;
  development_project_description: string | null;
  tae_hours: number | null;
  supervision_hours: number | null;
  default_online_students_per_class: number | null;
  timetable_locked: number;
  lecturing_hours: number | null;
  in_class_timetabled_hours: number | null;
  session_schedule_avg: string | null;
  variance: number | null;
  variance_category: string | null;
  bulk_online_detail: string | null;
  bulk_online_hours_avg: number | null;
  total_hours: number | null;
  preferences: { first: string[]; second: string[]; third: string[] };
  online_students: StaffOnlineStudentRow[];
};

export type StaffOnlineStudentRow = {
  unit_id: number;
  label: string;
  session_count: number;
  default_count: number;
  student_count: number;
};

export type QualificationDetail = {
  id: number;
  name: string;
  num_groups: number;
  schedule_period: string;
  delivery_mode: string;
  groups_summary: string;
  schedule_summary: string;
  block_status: string;
  regular_groups: { id: number; code: string }[];
  block_groups: { id: number; code: string }[];
  linked_classes: { id: number; name: string }[];
};

export type UnitConstraints = {
  unit_id: number;
  allowed_room_ids: number[];
  competent_staff_ids: number[];
};

export type LapRow = {
  unit_id: number;
  unit_name: string;
  component_codes: string | null;
  has_lap: boolean;
  original_filename: string | null;
  uploaded_at: string | null;
  timetable_lecturer_name: string;
};

export type LapList = {
  rows: LapRow[];
};

export type CreateBookingDraft = {
  courseId: number;
  day: number;
  startSlot: number;
  endSlot: number;
};

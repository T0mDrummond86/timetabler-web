export type Violation = {
  severity: string;
  code: string;
  message: string;
  booking_ids?: number[];
};

export type BookingCard = {
  id: number;
  day: number;
  start_slot: number;
  end_slot: number;
  lane: number;
  lane_depth: number;
  unit_name: string | null;
  course_code: string | null;
  staff_name: string | null;
  room_code: string | null;
  notes: string | null;
  external_id: string | null;
  colour_key: string;
  fill_colour: string;
  border_colour: string;
  is_hard: boolean;
  is_soft: boolean;
  violations: Violation[];
};

export type TimetableGrid = {
  timetable_session_id: number;
  course_id: number;
  course_code: string;
  week_id: number;
  week_label: string;
  days: string[];
  num_slots: number;
  slot_minutes: number;
  first_slot_time: string;
  bookings: BookingCard[];
  violations: Violation[];
};

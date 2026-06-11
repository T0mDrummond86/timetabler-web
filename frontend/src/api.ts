import {
  BlockDeliveryPanel,
  BlockOverview,
  BlockWeekUsage,
  BookingMutation,
  ChangeLogList,
  CourseSemesterSchedule,
  ImportReport,
  LapList,
  TimetableEntity,
  TimetableGrid,
  TimetableView,
  ViolationsReport,
} from "./types";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

export type TokenResponse = { access_token: string; token_type: string };
export type User = { id: number; email: string; name: string };
export type Organization = { id: number; name: string; slug: string; role: string };
export type TimetableSession = {
  id: number;
  organization_id: number;
  name: string;
  created_at: string;
  updated_at: string;
  global_session_id?: number | null;
  global_session_name?: string | null;
  course_count?: number;
  booking_count?: number;
};

export type GlobalSessionSummary = {
  id: number;
  organization_id: number;
  name: string;
  member_count: number;
  created_at: string;
  updated_at: string;
};

export type GlobalSession = {
  id: number;
  organization_id: number;
  name: string;
  created_at: string;
  updated_at: string;
  member_sessions: { id: number; name: string }[];
};

export type TimetableGlobalLink = {
  linked: boolean;
  global_session_id?: number;
  global_session_name?: string;
  member_session_ids?: number[];
};

export type TimetablePrintKind = "course" | "staff" | "room";

export type TimetablePrintEntity = { id: number; label: string };

export type TimetablePrintInfo = {
  week_label: string | null;
  entities: TimetablePrintEntity[];
};
export type Course = {
  id: number;
  code: string;
  name: string | null;
  timetable_locked?: number;
  block_week_count?: number | null;
  block_start_semester_week?: number | null;
};
export type Staff = {
  id: number;
  name: string;
  cost_centre?: string | null;
  max_hours_per_week?: number | null;
  fte?: number | null;
  non_teaching_day?: number | null;
  ot_hours?: number | null;
  development_project_hours?: number | null;
  development_project_description?: string | null;
  tae_hours?: number | null;
  supervision_hours?: number | null;
  default_online_students_per_class?: number | null;
  timetable_locked?: number;
};
export type Room = {
  id: number;
  code: string;
  name: string | null;
  room_type?: string | null;
  capacity?: number | null;
};
export type Unit = {
  id: number;
  name: string;
  length_slots?: number | null;
  component_codes?: string | null;
  double_session?: number;
  double_session_same_day?: number | null;
  double_session_first_slots?: number | null;
  screen_fill_colour?: string | null;
  qualification_ids?: number[];
};
export type Qualification = {
  id: number;
  name: string;
  num_groups?: number;
  schedule_period?: string;
};

export type GlobalAmalgamatedMember = {
  session_id: number;
  session_name: string;
  entity_id?: number | null;
};

export type GlobalAggregatedStaffRow = {
  name: string;
  session_names: string[];
  session_count: number;
  members?: GlobalAmalgamatedMember[];
  fte?: number | null | string;
  max_hours_per_week?: number | null | string;
  non_teaching_day?: number | null | string;
  variance?: number | null | string;
  member_variances?: (number | null)[];
};

export type GlobalAggregatedRoomRow = {
  code: string;
  session_names: string[];
  session_count: number;
  members?: GlobalAmalgamatedMember[];
  name?: string | null;
  room_type?: string | null;
  capacity?: number | null;
};

export type GlobalAggregatedUnitRow = {
  name: string;
  session_names: string[];
  session_count: number;
  members?: GlobalAmalgamatedMember[];
  qualifications?: string;
  length_slots?: number | null | string;
  double_session?: number | string;
  component_codes?: string | null | string;
};

export type GlobalAggregatedQualRow = {
  name: string;
  session_names: string[];
  session_count: number;
  members?: GlobalAmalgamatedMember[];
  num_groups?: number | string;
  schedule_period?: string;
  delivery_mode?: string;
};

const TOKEN_KEY = "timetabler_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  auth = true,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (err) {
    const base = API_BASE || "(same origin — set VITE_API_URL)";
    const hint =
      err instanceof TypeError
        ? `Cannot reach the API at ${base}. Check that the API is running (docker compose up) and you are using the app at http://localhost:5173.`
        : "Network error";
    throw new Error(hint);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    if (
      auth &&
      res.status === 401 &&
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/login") &&
      !window.location.pathname.startsWith("/register")
    ) {
      setToken(null);
      window.location.replace("/login");
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function timetablePath(
  sessionId: number,
  opts: {
    view?: TimetableView;
    courseId?: number | null;
    staffId?: number | null;
    day?: number | null;
    semesterWeek?: number | null;
    blockWeekIndex?: number | null;
    colourByClass?: boolean;
    hideDismissed?: boolean;
  },
): string {
  const params = new URLSearchParams();
  const view = opts.view ?? "course";
  params.set("view", view);

  if (opts.colourByClass === false) params.set("colour_by_class", "false");
  if (opts.hideDismissed === false) params.set("hide_dismissed", "false");

  const courseViews: TimetableView[] = ["course", "course_semester", "block_delivery"];
  if (courseViews.includes(view) && opts.courseId != null) {
    params.set("course_id", String(opts.courseId));
  }
  if (view === "staff" && opts.staffId != null) params.set("staff_id", String(opts.staffId));
  if ((view === "room" || view === "day") && opts.day != null) {
    params.set("day", String(opts.day));
  }
  if (view === "course_semester" && opts.semesterWeek != null) {
    params.set("semester_week", String(opts.semesterWeek));
  }
  if (view === "block_delivery" && opts.blockWeekIndex != null) {
    params.set("block_week_index", String(opts.blockWeekIndex));
  }
  return `/sessions/${sessionId}/timetable?${params.toString()}`;
}

function triggerAuthDownload(path: string): void {
  const token = getToken();
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (token) url.searchParams.set("access_token", token);
  const iframe = document.createElement("iframe");
  iframe.style.display = "none";
  iframe.setAttribute("aria-hidden", "true");
  document.body.appendChild(iframe);
  iframe.src = url.toString();
  window.setTimeout(() => {
    iframe.remove();
  }, 120_000);
}

export const api = {
  register: (body: {
    email: string;
    password: string;
    name: string;
    organization_name: string;
  }) => apiFetch<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(body) }, false),

  login: (body: { email: string; password: string; organization_id?: number }) =>
    apiFetch<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(body) }, false),

  me: () => apiFetch<User>("/auth/me"),

  orgs: () => apiFetch<Organization[]>("/orgs"),

  sessions: (orgId: number) => apiFetch<TimetableSession[]>(`/orgs/${orgId}/sessions`),

  globalSessions: (orgId: number) => apiFetch<GlobalSessionSummary[]>(`/orgs/${orgId}/global-sessions`),

  globalSession: (globalSessionId: number) =>
    apiFetch<GlobalSession>(`/global-sessions/${globalSessionId}`),

  createGlobalSession: (orgId: number, name: string) =>
    apiFetch<GlobalSession>(`/orgs/${orgId}/global-sessions`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  updateGlobalSession: (globalSessionId: number, name: string) =>
    apiFetch<GlobalSession>(`/global-sessions/${globalSessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),

  deleteGlobalSession: (globalSessionId: number) =>
    apiFetch<void>(`/global-sessions/${globalSessionId}`, { method: "DELETE" }),

  setGlobalSessionMembers: (globalSessionId: number, timetableSessionIds: number[]) =>
    apiFetch<GlobalSession>(`/global-sessions/${globalSessionId}/members`, {
      method: "PUT",
      body: JSON.stringify({ timetable_session_ids: timetableSessionIds }),
    }),

  globalSessionStaff: (globalSessionId: number) =>
    apiFetch<{ rows: GlobalAggregatedStaffRow[] }>(`/global-sessions/${globalSessionId}/staff`),

  globalSessionRooms: (globalSessionId: number) =>
    apiFetch<{ rows: GlobalAggregatedRoomRow[] }>(`/global-sessions/${globalSessionId}/rooms`),

  globalSessionUnits: (globalSessionId: number) =>
    apiFetch<{ rows: GlobalAggregatedUnitRow[] }>(`/global-sessions/${globalSessionId}/units`),

  globalSessionQualifications: (globalSessionId: number) =>
    apiFetch<{ rows: GlobalAggregatedQualRow[] }>(
      `/global-sessions/${globalSessionId}/qualifications`,
    ),

  globalSessionClassCustodians: (globalSessionId: number) =>
    apiFetch<import("./types").GlobalClassCustodians>(
      `/global-sessions/${globalSessionId}/class-custodians`,
    ),

  timetableGlobalLink: (sessionId: number) =>
    apiFetch<TimetableGlobalLink>(`/sessions/${sessionId}/global-link`),

  linkedSessions: (sessionId: number) =>
    apiFetch<{ sessions: { id: number; name: string }[] }>(
      `/sessions/${sessionId}/linked-sessions`,
    ),

  linkedImportOptions: (targetSessionId: number, sourceSessionId: number) =>
    apiFetch<{
      staff: { id: number; name: string; already_in_target: boolean }[];
      qualifications: {
        id: number;
        name: string;
        linked_classes: string[];
        already_in_target: boolean;
      }[];
    }>(
      `/sessions/${targetSessionId}/import-from-linked/options?source_session_id=${sourceSessionId}`,
    ),

  importFromLinkedSession: (
    targetSessionId: number,
    body: {
      source_session_id: number;
      staff_ids?: number[];
      qualification_ids?: number[];
    },
  ) =>
    apiFetch<{
      staff?: { added: string[]; skipped: { name: string; reason: string }[] };
      qualifications?: {
        added: string[];
        classes_added: string[];
        skipped: { name: string; reason: string }[];
      };
    }>(`/sessions/${targetSessionId}/import-from-linked`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  createSession: (orgId: number, name: string) =>
    apiFetch<TimetableSession>(`/orgs/${orgId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  courses: (sessionId: number) => apiFetch<Course[]>(`/sessions/${sessionId}/courses`),

  timetable: (
    sessionId: number,
    opts: {
      view?: TimetableView;
      courseId?: number | null;
      staffId?: number | null;
      day?: number | null;
      semesterWeek?: number | null;
      blockWeekIndex?: number | null;
      colourByClass?: boolean;
      hideDismissed?: boolean;
    },
  ) => apiFetch<TimetableGrid>(timetablePath(sessionId, opts)),

  timetableEntities: (sessionId: number, view: TimetableView | "block_overview") => {
    const params = new URLSearchParams({ view });
    return apiFetch<TimetableEntity[]>(
      `/sessions/${sessionId}/timetable-entities?${params.toString()}`,
    );
  },

  courseSemesterSchedule: (
    sessionId: number,
    courseId: number,
    semesterWeek?: number,
  ) => {
    const params = new URLSearchParams({ course_id: String(courseId) });
    if (semesterWeek != null) params.set("semester_week", String(semesterWeek));
    return apiFetch<CourseSemesterSchedule>(
      `/sessions/${sessionId}/course-semester-schedule?${params.toString()}`,
    );
  },

  toggleSemesterWeek: (
    sessionId: number,
    body: { booking_id: number; semester_week: number },
  ) =>
    apiFetch<CourseSemesterSchedule>(
      `/sessions/${sessionId}/course-semester-schedule/toggle-week`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  blockDeliveryPanel: (
    sessionId: number,
    opts: {
      qualificationId: number;
      courseId?: number | null;
      blockWeekIndex?: number | null;
    },
  ) => {
    const params = new URLSearchParams({
      qualification_id: String(opts.qualificationId),
    });
    if (opts.courseId != null) params.set("course_id", String(opts.courseId));
    if (opts.blockWeekIndex != null) {
      params.set("block_week_index", String(opts.blockWeekIndex));
    }
    return apiFetch<BlockDeliveryPanel>(
      `/sessions/${sessionId}/block-delivery-panel?${params.toString()}`,
    );
  },

  blockOverview: (sessionId: number) =>
    apiFetch<BlockOverview>(`/sessions/${sessionId}/block-overview`),

  blockWeekUsage: (sessionId: number, courseId: number, semesterWeek: number) => {
    const params = new URLSearchParams({
      course_id: String(courseId),
      semester_week: String(semesterWeek),
    });
    return apiFetch<BlockWeekUsage>(
      `/sessions/${sessionId}/block-week-usage?${params.toString()}`,
    );
  },

  seedDemo: (sessionId: number) =>
    apiFetch<{ course_id?: number; booking_count?: number; skipped?: boolean }>(
      `/sessions/${sessionId}/seed-demo`,
      { method: "POST" },
    ),

  staff: (sessionId: number) => apiFetch<Staff[]>(`/sessions/${sessionId}/staff`),

  rooms: (sessionId: number) => apiFetch<Room[]>(`/sessions/${sessionId}/rooms`),

  units: (sessionId: number) => apiFetch<Unit[]>(`/sessions/${sessionId}/units`),

  qualifications: (sessionId: number) => apiFetch<Qualification[]>(`/sessions/${sessionId}/qualifications`),

  patchStaff: (sessionId: number, staffId: number, body: Partial<Staff>) =>
    apiFetch<Staff>(`/sessions/${sessionId}/staff/${staffId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  patchRoom: (sessionId: number, roomId: number, body: Partial<Room>) =>
    apiFetch<Room>(`/sessions/${sessionId}/rooms/${roomId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  patchUnit: (sessionId: number, unitId: number, body: Partial<Unit>) =>
    apiFetch<Unit>(`/sessions/${sessionId}/units/${unitId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  patchCourse: (sessionId: number, courseId: number, body: Partial<Course>) =>
    apiFetch<Course>(`/sessions/${sessionId}/courses/${courseId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  patchQualification: (sessionId: number, qualificationId: number, body: Partial<Qualification>) =>
    apiFetch<Qualification>(`/sessions/${sessionId}/qualifications/${qualificationId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  moveBooking: (
    sessionId: number,
    bookingId: number,
    body: { course_id: number; day: number; start_slot: number; room_id?: number | null },
  ) =>
    apiFetch<BookingMutation>(`/sessions/${sessionId}/bookings/${bookingId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  patchBooking: (
    sessionId: number,
    bookingId: number,
    body: {
      course_id: number;
      day?: number;
      start_slot?: number;
      end_slot?: number;
      notes?: string | null;
      staff_id?: number | null;
      room_id?: number | null;
      unit_id?: number | null;
      external_id?: string | null;
      in_term_1?: number;
      in_term_2?: number;
      sfs_co_teacher_staff_id?: number | null;
      sfs_co_teacher_in_term_1?: number;
      sfs_co_teacher_in_term_2?: number;
      online_student_count?: number | null;
    },
  ) =>
    apiFetch<BookingMutation>(`/sessions/${sessionId}/bookings/${bookingId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  restoreBookings: (
    sessionId: number,
    body: {
      course_id: number;
      action: "undo" | "redo";
      label: string;
      snapshots: Record<string, Record<string, unknown> | null>;
    },
  ) =>
    apiFetch<BookingMutation>(`/sessions/${sessionId}/bookings/restore`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  holdingArea: (
    sessionId: number,
    opts: {
      kind?: "course" | "block" | "unassigned";
      courseId?: number;
      blockWeekIndex?: number;
    },
  ) => {
    const params = new URLSearchParams();
    const kind = opts.kind ?? "course";
    params.set("kind", kind);
    if (opts.courseId != null) params.set("course_id", String(opts.courseId));
    if (opts.blockWeekIndex != null) {
      params.set("block_week_index", String(opts.blockWeekIndex));
    }
    return apiFetch<
      {
        course_id: number;
        unit_id: number;
        unit_name: string | null;
        duration_slots: number;
        session_part: number;
      }[]
    >(`/sessions/${sessionId}/holding-area?${params.toString()}`);
  },

  createBooking: (
    sessionId: number,
    body: {
      course_id: number;
      unit_id: number;
      day: number;
      start_slot: number;
      end_slot: number;
      staff_id?: number | null;
      room_id?: number | null;
      session_part?: number;
      notes?: string | null;
      block_week_index?: number | null;
    },
  ) =>
    apiFetch<BookingMutation>(`/sessions/${sessionId}/bookings`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteBooking: (sessionId: number, bookingId: number, courseId: number) =>
    apiFetch<BookingMutation>(
      `/sessions/${sessionId}/bookings/${bookingId}?course_id=${courseId}`,
      { method: "DELETE" },
    ),

  async importSession(sessionId: number, file: File): Promise<ImportReport> {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/import`, {
      method: "POST",
      headers,
      body: form,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return res.json() as Promise<ImportReport>;
  },

  async exportSessionJson(sessionId: number): Promise<void> {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/export/json`, { headers });
    if (!res.ok) throw new Error("Export failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `session-${sessionId}-backup.json`;
    a.click();
    URL.revokeObjectURL(url);
  },

  health: () => apiFetch<{ status: string; database: string; phase: number }>("/health", {}, false),

  changeLog: (sessionId: number, resolved = false) =>
    apiFetch<ChangeLogList>(
      `/sessions/${sessionId}/change-log?resolved=${resolved ? "true" : "false"}`,
    ),

  setChangeLogNote: (
    sessionId: number,
    entryId: number,
    body: { booking_id: number; note: string },
  ) =>
    apiFetch<{ ok: boolean }>(
      `/sessions/${sessionId}/change-log/entries/${entryId}/notes`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  rollbackChangeLog: (
    sessionId: number,
    body: { booking_id: number; course_id: number },
  ) =>
    apiFetch<BookingMutation>(`/sessions/${sessionId}/change-log/rollback`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  async exportChangeLog(sessionId: number): Promise<void> {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(
      `${API_BASE}/sessions/${sessionId}/change-log/export?resolved=true`,
      { headers },
    );
    if (!res.ok) throw new Error("Export failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "change_log_resolved.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  },

  violationsReport: (sessionId: number, severity?: "hard" | "soft") => {
    const params = new URLSearchParams();
    if (severity) params.set("severity", severity);
    const q = params.toString();
    return apiFetch<ViolationsReport>(
      `/sessions/${sessionId}/violations-report${q ? `?${q}` : ""}`,
    );
  },

  sidebarOrder: (sessionId: number, body: { view: "course" | "staff"; entity_ids: number[] }) =>
    apiFetch<{ ok: boolean }>(`/sessions/${sessionId}/sidebar-order`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  createBlock: (sessionId: number, qualificationId: number) =>
    apiFetch<{ qualification_id: number; course_id: number; course_code: string }>(
      `/sessions/${sessionId}/qualifications/${qualificationId}/create-block`,
      { method: "POST" },
    ),

  suggestedBlockCode: (sessionId: number, qualificationId: number) =>
    apiFetch<{ code: string | null }>(
      `/sessions/${sessionId}/block-groups/suggested-code?qualification_id=${qualificationId}`,
    ),

  duplicateBlockGroup: (sessionId: number, courseId: number, newCode: string) =>
    apiFetch<{ course_id: number; course_code: string }>(
      `/sessions/${sessionId}/block-groups/${courseId}/duplicate`,
      { method: "POST", body: JSON.stringify({ new_code: newCode }) },
    ),

  deleteBlockGroup: (sessionId: number, courseId: number) =>
    apiFetch<{ deleted: boolean; qualification_reverted: boolean }>(
      `/sessions/${sessionId}/block-groups/${courseId}`,
      { method: "DELETE" },
    ),

  patchBookingLocks: (
    sessionId: number,
    bookingId: number,
    body: { course_id: number; lock_time?: number; lock_staff?: number },
  ) =>
    apiFetch<BookingMutation>(`/sessions/${sessionId}/bookings/${bookingId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  alternateSlots: (
    sessionId: number,
    bookingId: number,
    opts?: { timesOnly?: boolean; fixedRoomId?: number },
  ) => {
    const params = new URLSearchParams();
    if (opts?.timesOnly) params.set("times_only", "true");
    if (opts?.fixedRoomId != null) params.set("fixed_room_id", String(opts.fixedRoomId));
    const q = params.toString();
    return apiFetch<import("./types").AlternateSlots>(
      `/sessions/${sessionId}/bookings/${bookingId}/alternate-slots${q ? `?${q}` : ""}`,
    );
  },

  classCustodians: (sessionId: number) =>
    apiFetch<import("./types").ClassCustodians>(`/sessions/${sessionId}/class-custodians`),

  staffAvailability: (sessionId: number, staffId: number) =>
    apiFetch<import("./types").StaffAvailability>(
      `/sessions/${sessionId}/staff/${staffId}/availability`,
    ),

  saveStaffAvailability: (sessionId: number, staffId: number, blocked: { day: number; slot: number }[]) =>
    apiFetch<import("./types").StaffAvailability>(
      `/sessions/${sessionId}/staff/${staffId}/availability`,
      { method: "PUT", body: JSON.stringify({ blocked }) },
    ),

  createStaff: (sessionId: number, name: string) =>
    apiFetch<Staff>(`/sessions/${sessionId}/staff`, { method: "POST", body: JSON.stringify({ name }) }),

  deleteStaff: (sessionId: number, staffId: number) =>
    apiFetch<{ deleted: boolean }>(`/sessions/${sessionId}/staff/${staffId}`, { method: "DELETE" }),

  createRoom: (sessionId: number, code: string) =>
    apiFetch<Room>(`/sessions/${sessionId}/rooms`, { method: "POST", body: JSON.stringify({ code }) }),

  deleteRoom: (sessionId: number, roomId: number) =>
    apiFetch<{ deleted: boolean }>(`/sessions/${sessionId}/rooms/${roomId}`, { method: "DELETE" }),

  createUnit: (sessionId: number, name: string) =>
    apiFetch<Unit>(`/sessions/${sessionId}/units`, { method: "POST", body: JSON.stringify({ name }) }),

  deleteUnit: (sessionId: number, unitId: number) =>
    apiFetch<{ deleted: boolean }>(`/sessions/${sessionId}/units/${unitId}`, { method: "DELETE" }),

  setUnitQualifications: (sessionId: number, unitId: number, qualificationIds: number[]) =>
    apiFetch<Unit>(`/sessions/${sessionId}/units/${unitId}/qualifications`, {
      method: "PUT",
      body: JSON.stringify({ qualification_ids: qualificationIds }),
    }),

  createQualification: (sessionId: number, name: string, schedulePeriod = "day") =>
    apiFetch<Qualification>(`/sessions/${sessionId}/qualifications`, {
      method: "POST",
      body: JSON.stringify({ name, schedule_period: schedulePeriod }),
    }),

  deleteQualification: (sessionId: number, qualificationId: number) =>
    apiFetch<{ deleted: boolean }>(`/sessions/${sessionId}/qualifications/${qualificationId}`, {
      method: "DELETE",
    }),

  createCourse: (sessionId: number, code: string) =>
    apiFetch<Course>(`/sessions/${sessionId}/courses`, {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  duplicateCourse: (sessionId: number, courseId: number, newCode: string) =>
    apiFetch<Course>(`/sessions/${sessionId}/courses/${courseId}/duplicate`, {
      method: "POST",
      body: JSON.stringify({ new_code: newCode }),
    }),

  deleteCourse: (sessionId: number, courseId: number) =>
    apiFetch<{ deleted: boolean }>(`/sessions/${sessionId}/courses/${courseId}`, { method: "DELETE" }),

  staffUsage: (sessionId: number) =>
    apiFetch<import("./types").ResourceUsage>(`/sessions/${sessionId}/usage/staff`),

  roomUsage: (sessionId: number) =>
    apiFetch<import("./types").ResourceUsage>(`/sessions/${sessionId}/usage/rooms`),

  patchSession: (sessionId: number, name: string) =>
    apiFetch<TimetableSession>(`/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),

  deleteSession: (sessionId: number) =>
    apiFetch<void>(`/sessions/${sessionId}`, { method: "DELETE" }),

  duplicateSession: (sessionId: number, name: string) =>
    apiFetch<TimetableSession>(`/sessions/${sessionId}/duplicate`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  dismissViolation: (sessionId: number, bookingId: number, code: string) =>
    apiFetch<{ ok: boolean }>(`/sessions/${sessionId}/violation-dismissals`, {
      method: "POST",
      body: JSON.stringify({ booking_id: bookingId, code }),
    }),

  staffDetail: (sessionId: number, staffId: number) =>
    apiFetch<import("./types").StaffDetail>(`/sessions/${sessionId}/staff/${staffId}/detail`),

  staffHoursTable: (sessionId: number) =>
    apiFetch<import("./types").StaffHoursRow[]>(`/sessions/${sessionId}/staff/hours-table`),

  saveStaffPreferences: (
    sessionId: number,
    staffId: number,
    prefs: { first: string[]; second: string[]; third: string[] },
  ) =>
    apiFetch<{ ok: boolean }>(`/sessions/${sessionId}/staff/${staffId}/preferences`, {
      method: "PUT",
      body: JSON.stringify(prefs),
    }),

  saveStaffOnlineStudents: (
    sessionId: number,
    staffId: number,
    counts: { unit_id: number; student_count: number | null }[],
  ) =>
    apiFetch<{ ok: boolean }>(`/sessions/${sessionId}/staff/${staffId}/online-students`, {
      method: "PUT",
      body: JSON.stringify({ counts }),
    }),

  qualificationDetail: (sessionId: number, qualificationId: number) =>
    apiFetch<import("./types").QualificationDetail>(
      `/sessions/${sessionId}/qualifications/${qualificationId}/detail`,
    ),

  unitConstraints: (sessionId: number, unitId: number) =>
    apiFetch<import("./types").UnitConstraints>(`/sessions/${sessionId}/units/${unitId}/constraints`),

  setUnitAllowedRooms: (sessionId: number, unitId: number, roomIds: number[]) =>
    apiFetch<import("./types").UnitConstraints>(
      `/sessions/${sessionId}/units/${unitId}/allowed-rooms`,
      { method: "PUT", body: JSON.stringify({ room_ids: roomIds }) },
    ),

  setUnitCompetencies: (sessionId: number, unitId: number, staffIds: number[]) =>
    apiFetch<import("./types").UnitConstraints>(
      `/sessions/${sessionId}/units/${unitId}/competencies`,
      { method: "PUT", body: JSON.stringify({ staff_ids: staffIds }) },
    ),

  splitUnitsFromBrackets: (sessionId: number) =>
    apiFetch<{ updated: number }>(`/sessions/${sessionId}/units/split-from-brackets`, {
      method: "POST",
    }),

  setStaffCompetencies: (sessionId: number, staffId: number, unitIds: number[]) =>
    apiFetch<{ unit_ids: number[] }>(`/sessions/${sessionId}/staff/${staffId}/competencies`, {
      method: "PUT",
      body: JSON.stringify({ unit_ids: unitIds }),
    }),

  roomTypeChoices: () =>
    apiFetch<{ choices: [string, string][] }>("/room-type-choices"),

  timetablePrintInfo: (sessionId: number, kind: TimetablePrintKind) =>
    apiFetch<TimetablePrintInfo>(
      `/sessions/${sessionId}/print/timetables/info?kind=${encodeURIComponent(kind)}`,
    ),

  async downloadTimetablePrintPdf(
    sessionId: number,
    body: {
      kind: TimetablePrintKind;
      term_filter: "all" | "t1" | "t2";
      colour_by_class: boolean;
      include_index?: boolean;
      entities: TimetablePrintEntity[];
    },
  ): Promise<void> {
    const token = getToken();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/sessions/${sessionId}/print/timetables`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
    } catch {
      throw new Error(
        "Cannot reach the API. Check that the API is running and you are using http://localhost:5173.",
      );
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "timetables_print.pdf";
    a.click();
    URL.revokeObjectURL(url);
  },

  /** Start a file download in the same user gesture (avoids multi-click blob downloads). */
  downloadExport(path: string, _filename: string): void {
    triggerAuthDownload(path);
  },

  async importFile(sessionId: number, kind: "session" | "qualifications" | "qualifications-csp" | "qualifications-ep-nb-csp" | "asc" | "lecturer-preferences" | "overall-visual" | "admin-visual", file: File) {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const form = new FormData();
    form.append("file", file);
    const paths: Record<string, string> = {
      session: `/sessions/${sessionId}/import`,
      qualifications: `/sessions/${sessionId}/import/qualifications`,
      "qualifications-csp": `/sessions/${sessionId}/import/qualifications-csp`,
      "qualifications-ep-nb-csp": `/sessions/${sessionId}/import/qualifications-ep-nb-csp`,
      asc: `/sessions/${sessionId}/import/asc`,
      "lecturer-preferences": `/sessions/${sessionId}/import/lecturer-preferences`,
      "overall-visual": `/sessions/${sessionId}/import/overall-visual`,
      "admin-visual": `/sessions/${sessionId}/import/admin-visual`,
    };
    const res = await fetch(`${API_BASE}${paths[kind]}`, { method: "POST", headers, body: form });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return res.json();
  },

  lapList: (sessionId: number) => apiFetch<LapList>(`/sessions/${sessionId}/laps`),

  async lapUpload(sessionId: number, unitId: number, file: File): Promise<void> {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/laps/${unitId}`, {
      method: "POST",
      headers,
      body: form,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
  },

  lapDelete: (sessionId: number, unitId: number) =>
    apiFetch<void>(`/sessions/${sessionId}/laps/${unitId}`, { method: "DELETE" }),

  lapDownload(sessionId: number, unitId: number, deliveryPeriod?: string) {
    const params = new URLSearchParams();
    const period = deliveryPeriod?.trim();
    if (period) params.set("delivery_period", period);
    const qs = params.toString();
    triggerAuthDownload(
      `/sessions/${sessionId}/laps/${unitId}/download${qs ? `?${qs}` : ""}`,
    );
  },

  lapDownloadAll(sessionId: number, deliveryPeriod?: string) {
    const params = new URLSearchParams();
    const period = deliveryPeriod?.trim();
    if (period) params.set("delivery_period", period);
    const qs = params.toString();
    triggerAuthDownload(
      `/sessions/${sessionId}/laps/download-all${qs ? `?${qs}` : ""}`,
    );
  },
};

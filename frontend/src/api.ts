import { TimetableGrid } from "./types";

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
};
export type Course = { id: number; code: string; name: string | null };

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
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
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
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
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

  createSession: (orgId: number, name: string) =>
    apiFetch<TimetableSession>(`/orgs/${orgId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  courses: (sessionId: number) => apiFetch<Course[]>(`/sessions/${sessionId}/courses`),

  timetable: (sessionId: number, courseId: number) =>
    apiFetch<TimetableGrid>(
      `/sessions/${sessionId}/timetable?course_id=${courseId}`,
    ),

  seedDemo: (sessionId: number) =>
    apiFetch<{ course_id?: number; booking_count?: number; skipped?: boolean }>(
      `/sessions/${sessionId}/seed-demo`,
      { method: "POST" },
    ),

  health: () => apiFetch<{ status: string; database: string; phase: number }>("/health", {}, false),
};

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, Course, Qualification, Room, Staff, Unit } from "../api";
import type { QualificationDetail, StaffHoursRow, StaffOnlineStudentRow } from "../types";
import {
  blockedApiFromSet,
  blockedSetFromApi,
  StaffAvailabilityGrid,
} from "./StaffAvailabilityGrid";
import { StaffHoursTable } from "./StaffHoursTable";
import { LinkedSessionImportPanel } from "./LinkedSessionImportPanel";

type Tab = "staff" | "rooms" | "units" | "courses" | "qualifications";

function parsePrefClasses(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 2);
}

function joinPrefClasses(names: string[]): string {
  return names.join(", ");
}

function isOnCampusRoom(room: Room): boolean {
  const t = (room.room_type ?? "").toLowerCase();
  return !t || t === "on-campus" || t === "general";
}

function roomTypeLabel(room: Room, choices: [string, string][]): string {
  const t = room.room_type ?? "";
  const hit = choices.find(([v]) => v === t);
  return hit ? hit[1] : t || "On-campus";
}

export type EntityUpdateHint = {
  blockCourseId?: number;
  qualificationId?: number;
};

type Props = {
  sessionId: number;
  staff: Staff[];
  rooms: Room[];
  units: Unit[];
  courses: Course[];
  qualifications: Qualification[];
  onUpdated: (hint?: EntityUpdateHint) => void;
  /** When set, show only this entity editor (desktop-style dedicated tab). */
  fixedTab?: Tab;
  /** Select this entity when the panel mounts (e.g. jump from Qualifications → Classes). */
  focusEntityId?: number | null;
  onFocusConsumed?: () => void;
  /** Open the Classes tab for this unit (desktop navigateToClass). */
  onNavigateToUnit?: (unitId: number) => void;
  /** Show import-from-linked panel on staff / qualifications tabs. */
  showLinkedImport?: boolean;
  /** Increment to reload staff hours/detail after a change in a linked session tab. */
  syncToken?: number;
};

export function EntityEditorsPanel({
  sessionId,
  staff,
  rooms,
  units,
  courses,
  qualifications,
  onUpdated,
  fixedTab,
  focusEntityId,
  onFocusConsumed,
  onNavigateToUnit,
  showLinkedImport = false,
  syncToken = 0,
}: Props) {
  const [tab, setTab] = useState<Tab>(fixedTab ?? "staff");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [blockedSlots, setBlockedSlots] = useState<Set<string>>(new Set());
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [unitQualIds, setUnitQualIds] = useState<number[]>([]);
  const [allowedRoomIds, setAllowedRoomIds] = useState<number[]>([]);
  const [staffDetail, setStaffDetail] = useState<import("../types").StaffDetail | null>(null);
  const [prefFirst, setPrefFirst] = useState("");
  const [prefSecond, setPrefSecond] = useState("");
  const [prefThird, setPrefThird] = useState("");
  const [onlineRows, setOnlineRows] = useState<StaffOnlineStudentRow[]>([]);
  const [qualDetail, setQualDetail] = useState<QualificationDetail | null>(null);
  const [competentStaffIds, setCompetentStaffIds] = useState<number[]>([]);
  const [lecturerSearch, setLecturerSearch] = useState("");
  const [unitSearch, setUnitSearch] = useState("");
  const [unitQualFilter, setUnitQualFilter] = useState<number | "">("");
  const [roomTypeChoices, setRoomTypeChoices] = useState<[string, string][]>([]);
  const [staffHoursRows, setStaffHoursRows] = useState<StaffHoursRow[]>([]);
  const [staffHoursLoading, setStaffHoursLoading] = useState(false);
  const [unitDoubleSession, setUnitDoubleSession] = useState(false);

  useEffect(() => {
    if (fixedTab) setTab(fixedTab);
  }, [fixedTab]);

  const activeTab = fixedTab ?? tab;

  const reloadStaffHours = useCallback(async () => {
    if (activeTab !== "staff") return;
    setStaffHoursLoading(true);
    try {
      setStaffHoursRows(await api.staffHoursTable(sessionId));
    } catch {
      setStaffHoursRows([]);
    } finally {
      setStaffHoursLoading(false);
    }
  }, [activeTab, sessionId]);

  useEffect(() => {
    void reloadStaffHours();
  }, [reloadStaffHours, syncToken]);

  useEffect(() => {
    if (focusEntityId == null) return;
    if (fixedTab !== "units" && activeTab !== "units") return;
    setSelectedId(focusEntityId);
    setMessage(null);
    setError(null);
    onFocusConsumed?.();
  }, [focusEntityId, fixedTab, activeTab, onFocusConsumed]);

  useEffect(() => {
    if (activeTab !== "staff" || selectedId == null) {
      setBlockedSlots(new Set());
      return;
    }
    let cancelled = false;
    setAvailabilityLoading(true);
    (async () => {
      try {
        const data = await api.staffAvailability(sessionId, selectedId);
        if (!cancelled) setBlockedSlots(blockedSetFromApi(data.blocked));
      } catch {
        if (!cancelled) setBlockedSlots(new Set());
      } finally {
        if (!cancelled) setAvailabilityLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, activeTab, selectedId]);

  useEffect(() => {
    api.roomTypeChoices().then((r) => setRoomTypeChoices(r.choices)).catch(() => setRoomTypeChoices([]));
  }, []);

  useEffect(() => {
    if (activeTab === "staff" && selectedId != null) {
      api.staffDetail(sessionId, selectedId).then(setStaffDetail).catch(() => setStaffDetail(null));
    } else {
      setStaffDetail(null);
    }
  }, [sessionId, activeTab, selectedId, syncToken]);

  useEffect(() => {
    if (!staffDetail) {
      setPrefFirst("");
      setPrefSecond("");
      setPrefThird("");
      setOnlineRows([]);
      return;
    }
    setPrefFirst(joinPrefClasses(staffDetail.preferences.first));
    setPrefSecond(joinPrefClasses(staffDetail.preferences.second));
    setPrefThird(joinPrefClasses(staffDetail.preferences.third));
    setOnlineRows(staffDetail.online_students.map((r) => ({ ...r })));
  }, [staffDetail]);

  useEffect(() => {
    if (activeTab === "qualifications" && selectedId != null) {
      api
        .qualificationDetail(sessionId, selectedId)
        .then(setQualDetail)
        .catch(() => setQualDetail(null));
    } else {
      setQualDetail(null);
    }
  }, [sessionId, activeTab, selectedId]);

  useEffect(() => {
    if (activeTab === "units" && selectedId != null) {
      const unit = units.find((u) => u.id === selectedId);
      setUnitQualIds(unit?.qualification_ids ?? []);
    } else {
      setUnitQualIds([]);
    }
  }, [activeTab, selectedId, units]);

  useEffect(() => {
    if (activeTab === "units" && selectedId != null) {
      api
        .unitConstraints(sessionId, selectedId)
        .then((c) => {
          setAllowedRoomIds(c.allowed_room_ids);
          setCompetentStaffIds(c.competent_staff_ids);
        })
        .catch(() => {
          setAllowedRoomIds([]);
          setCompetentStaffIds([]);
        });
    } else {
      setAllowedRoomIds([]);
      setCompetentStaffIds([]);
    }
  }, [sessionId, activeTab, selectedId]);

  const baseRows: { id: number; label: string }[] =
    activeTab === "staff"
      ? staff.map((s) => ({ id: s.id, label: s.name }))
      : activeTab === "rooms"
        ? rooms.map((r) => ({ id: r.id, label: r.code }))
        : activeTab === "units"
          ? units.map((u) => ({ id: u.id, label: u.name }))
          : activeTab === "courses"
            ? courses.map((c) => ({ id: c.id, label: c.code }))
            : qualifications.map((q) => ({ id: q.id, label: q.name }));

  const rows = useMemo(() => {
    if (activeTab !== "units") return baseRows;
    const q = unitSearch.trim().toLowerCase();
    return baseRows.filter((row) => {
      const unit = units.find((u) => u.id === row.id);
      if (!unit) return false;
      if (unitQualFilter !== "" && !(unit.qualification_ids ?? []).includes(unitQualFilter)) {
        return false;
      }
      if (q && !unit.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [activeTab, baseRows, units, unitSearch, unitQualFilter]);

  const onCampusRoomIds = useMemo(
    () => rooms.filter(isOnCampusRoom).map((r) => r.id),
    [rooms],
  );
  const allOnCampusSelected =
    onCampusRoomIds.length > 0 && onCampusRoomIds.every((id) => allowedRoomIds.includes(id));

  const filteredStaffForUnit = useMemo(() => {
    const q = lecturerSearch.trim().toLowerCase();
    return staff.filter((s) => !q || s.name.toLowerCase().includes(q));
  }, [staff, lecturerSearch]);

  const selectedStaff = staff.find((s) => s.id === selectedId);
  const selectedRoom = rooms.find((r) => r.id === selectedId);
  const selectedUnit = units.find((u) => u.id === selectedId);
  const selectedCourse = courses.find((c) => c.id === selectedId);
  const selectedQual = qualifications.find((q) => q.id === selectedId);

  useEffect(() => {
    setUnitDoubleSession(!!selectedUnit?.double_session);
  }, [selectedUnit?.id, selectedUnit?.double_session]);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (selectedId == null) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    const form = new FormData(e.currentTarget);
    try {
      if (activeTab === "staff" && selectedStaff) {
        await api.patchStaff(sessionId, selectedId, {
          name: String(form.get("name") || selectedStaff.name),
          fte: form.get("fte") ? Number(form.get("fte")) : null,
          non_teaching_day: form.get("non_teaching_day")
            ? Number(form.get("non_teaching_day"))
            : null,
          development_project_hours: form.get("development_project_hours")
            ? Number(form.get("development_project_hours"))
            : null,
          development_project_description:
            String(form.get("development_project_description") || "") || null,
          tae_hours: form.get("tae_hours") ? Number(form.get("tae_hours")) : null,
          supervision_hours: form.get("supervision_hours")
            ? Number(form.get("supervision_hours"))
            : null,
          default_online_students_per_class: form.get("default_online_students_per_class")
            ? Number(form.get("default_online_students_per_class"))
            : null,
          timetable_locked: form.get("timetable_locked") === "on" ? 1 : 0,
        });
        await api.saveStaffAvailability(sessionId, selectedId, blockedApiFromSet(blockedSlots));
        await api.saveStaffPreferences(sessionId, selectedId, {
          first: parsePrefClasses(prefFirst),
          second: parsePrefClasses(prefSecond),
          third: parsePrefClasses(prefThird),
        });
        await api.saveStaffOnlineStudents(
          sessionId,
          selectedId,
          onlineRows.map((r) => ({
            unit_id: r.unit_id,
            student_count: r.student_count === r.default_count ? null : r.student_count,
          })),
        );
        const refreshed = await api.staffDetail(sessionId, selectedId);
        setStaffDetail(refreshed);
        await reloadStaffHours();
      } else if (activeTab === "rooms" && selectedRoom) {
        await api.patchRoom(sessionId, selectedId, {
          code: String(form.get("code") || selectedRoom.code),
          name: String(form.get("name") || "") || null,
          room_type: String(form.get("room_type") || "") || null,
          capacity: form.get("capacity") ? Number(form.get("capacity")) : null,
        });
      } else if (activeTab === "units" && selectedUnit) {
        const lengthHours = form.get("length_hours") ? Number(form.get("length_hours")) : 0;
        const lengthSlots = lengthHours > 0 ? Math.round(lengthHours * 2) : null;
        const isDouble = form.get("double_session") === "on";
        let double_session_first_slots: number | null = null;
        if (isDouble && lengthSlots) {
          const firstHours = form.get("double_session_first_hours")
            ? Number(form.get("double_session_first_hours"))
            : lengthHours / 2;
          let firstSlots = Math.max(1, Math.round(firstHours * 2));
          if (firstSlots >= lengthSlots) {
            firstSlots = Math.max(1, Math.floor(lengthSlots / 2));
          }
          double_session_first_slots = firstSlots;
        }
        await api.patchUnit(sessionId, selectedId, {
          name: String(form.get("name") || selectedUnit.name),
          length_slots: lengthSlots,
          component_codes: String(form.get("component_codes") || "") || null,
          double_session: isDouble ? 1 : 0,
          double_session_same_day: form.get("double_session_same_day") === "on" ? 1 : 0,
          double_session_first_slots,
        });
        await api.setUnitQualifications(sessionId, selectedId, unitQualIds);
        await api.setUnitAllowedRooms(sessionId, selectedId, allowedRoomIds);
        await api.setUnitCompetencies(sessionId, selectedId, competentStaffIds);
      } else if (activeTab === "courses" && selectedCourse) {
        await api.patchCourse(sessionId, selectedId, {
          code: String(form.get("code") || selectedCourse.code),
          name: String(form.get("name") || "") || null,
          timetable_locked: form.get("timetable_locked") === "on" ? 1 : 0,
        });
      } else if (activeTab === "qualifications" && selectedQual) {
        await api.patchQualification(sessionId, selectedId, {
          name: String(form.get("name") || selectedQual.name),
          num_groups: form.get("num_groups") ? Number(form.get("num_groups")) : undefined,
          schedule_period: String(form.get("schedule_period") || selectedQual.schedule_period || "day"),
        });
        const detail = await api.qualificationDetail(sessionId, selectedId);
        setQualDetail(detail);
      }
      setMessage("Saved");
      if (activeTab === "qualifications" && selectedId != null) {
        onUpdated({ qualificationId: selectedId });
      } else {
        onUpdated();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function onTabChange(next: Tab) {
    setTab(next);
    setSelectedId(null);
    setError(null);
    setMessage(null);
  }

  async function addEntity() {
    const label = window.prompt(
      activeTab === "staff"
        ? "Staff name:"
        : activeTab === "rooms"
          ? "Room code:"
          : activeTab === "units"
            ? "Class name:"
            : "Qualification name:",
    );
    if (!label?.trim()) return;
    setSaving(true);
    setError(null);
    try {
      if (activeTab === "staff") {
        await api.createStaff(sessionId, label.trim());
        await reloadStaffHours();
      }
      else if (activeTab === "rooms") await api.createRoom(sessionId, label.trim());
      else if (activeTab === "units") await api.createUnit(sessionId, label.trim());
      else if (activeTab === "qualifications") await api.createQualification(sessionId, label.trim());
      setMessage("Added");
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Add failed");
    } finally {
      setSaving(false);
    }
  }

  async function deleteEntity() {
    if (selectedId == null) return;
    const row = rows.find((r) => r.id === selectedId);
    if (!window.confirm(`Delete ${row?.label ?? "this item"}?`)) return;
    setSaving(true);
    setError(null);
    try {
      if (activeTab === "staff") {
        await api.deleteStaff(sessionId, selectedId);
        await reloadStaffHours();
      }
      else if (activeTab === "rooms") await api.deleteRoom(sessionId, selectedId);
      else if (activeTab === "units") await api.deleteUnit(sessionId, selectedId);
      else if (activeTab === "qualifications") await api.deleteQualification(sessionId, selectedId);
      setSelectedId(null);
      setMessage("Deleted");
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel">
      {!fixedTab && (
      <div className="panel-header">
        <h2>Entity editors</h2>
      </div>
      )}
      {showLinkedImport && (activeTab === "staff" || activeTab === "qualifications") && (
        <LinkedSessionImportPanel
          targetSessionId={sessionId}
          onImported={() => onUpdated()}
          importStaff={activeTab === "staff"}
          importQualifications={activeTab === "qualifications"}
        />
      )}

      {!fixedTab && (
      <div className="entity-tabs">
        {(["staff", "rooms", "units", "courses", "qualifications"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            className={`btn-secondary${activeTab === t ? " active-tab" : ""}`}
            onClick={() => onTabChange(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      )}
      <div
        className={
          activeTab === "staff" ? "entity-editor-layout staff-editor-layout" : "entity-editor-layout"
        }
      >
        <div className={activeTab === "staff" ? "entity-list-col staff-hours-list-col" : "entity-list-col"}>
          {activeTab === "units" && (
            <div className="entity-list-filters">
              <input
                type="search"
                className="field-input"
                placeholder="Search classes…"
                value={unitSearch}
                onChange={(e) => setUnitSearch(e.target.value)}
                aria-label="Search classes"
              />
              <select
                className="field-select"
                value={unitQualFilter === "" ? "" : String(unitQualFilter)}
                onChange={(e) =>
                  setUnitQualFilter(e.target.value === "" ? "" : Number(e.target.value))
                }
                aria-label="Filter by qualification"
              >
                <option value="">All qualifications</option>
                {qualifications.map((q) => (
                  <option key={q.id} value={q.id}>
                    {q.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          {fixedTab && fixedTab !== "courses" && (
            <div className="entity-list-toolbar">
              <button type="button" className="btn-secondary btn-xs" onClick={() => void addEntity()} disabled={saving}>
                Add
              </button>
              <button
                type="button"
                className="btn-secondary btn-xs"
                onClick={() => void deleteEntity()}
                disabled={saving || selectedId == null}
              >
                Delete
              </button>
            </div>
          )}
          {activeTab === "staff" ? (
            <StaffHoursTable
              rows={staffHoursRows}
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                setMessage(null);
                setError(null);
              }}
              loading={staffHoursLoading}
            />
          ) : (
            <ul className="entity-list">
              {rows.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    className={selectedId === row.id ? "entity-item active" : "entity-item"}
                    onClick={() => {
                      setSelectedId(row.id);
                      setMessage(null);
                      setError(null);
                    }}
                  >
                    {row.label}
                  </button>
                </li>
              ))}
              {!rows.length && <li className="tt-entity-empty">No {activeTab} in this session.</li>}
            </ul>
          )}
        </div>
        <div className="entity-form-wrap">
          {selectedId == null && <p className="muted">Select an item to edit.</p>}
          {selectedStaff && activeTab === "staff" && (
            <form key={selectedStaff.id} className="form" onSubmit={save}>
              <label>
                Name
                <input name="name" defaultValue={selectedStaff.name} required />
              </label>
              <label>
                FTE
                <input name="fte" type="number" step="0.1" defaultValue={selectedStaff.fte ?? ""} />
              </label>
              <label>
                Non-teaching day
                <select name="non_teaching_day" defaultValue={selectedStaff.non_teaching_day ?? ""}>
                  <option value="">—</option>
                  {["Mon", "Tue", "Wed", "Thu", "Fri"].map((d, i) => (
                    <option key={d} value={i}>
                      {d}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Development & project hours
                <input
                  name="development_project_hours"
                  type="number"
                  step="0.5"
                  defaultValue={selectedStaff.development_project_hours ?? ""}
                />
              </label>
              <label>
                Development description
                <input
                  name="development_project_description"
                  defaultValue={selectedStaff.development_project_description ?? ""}
                />
              </label>
              <label>
                PD / training (TAE)
                <input name="tae_hours" type="number" step="0.5" defaultValue={selectedStaff.tae_hours ?? ""} />
              </label>
              <label>
                Supervision hours
                <input
                  name="supervision_hours"
                  type="number"
                  step="0.5"
                  defaultValue={selectedStaff.supervision_hours ?? ""}
                />
              </label>
              <label>
                Default online students / class
                <input
                  name="default_online_students_per_class"
                  type="number"
                  min={0}
                  defaultValue={selectedStaff.default_online_students_per_class ?? ""}
                />
              </label>
              <fieldset className="qual-link-fieldset">
                <legend>Class preferences (comma-separated, up to 2 each)</legend>
                <label>
                  1st preference
                  <input
                    value={prefFirst}
                    onChange={(e) => setPrefFirst(e.target.value)}
                    placeholder="e.g. Class A, Class B"
                  />
                </label>
                <label>
                  2nd preference
                  <input
                    value={prefSecond}
                    onChange={(e) => setPrefSecond(e.target.value)}
                  />
                </label>
                <label>
                  3rd preference
                  <input value={prefThird} onChange={(e) => setPrefThird(e.target.value)} />
                </label>
              </fieldset>
              {onlineRows.length > 0 && (
                <fieldset className="qual-link-fieldset">
                  <legend>Online students per class</legend>
                  <p className="muted entity-hint">
                    Totals apply when a booking has no per-session class size. Each row is one class.
                  </p>
                  <table className="entity-mini-table">
                    <thead>
                      <tr>
                        <th>Class</th>
                        <th>Sessions</th>
                        <th>Students</th>
                      </tr>
                    </thead>
                    <tbody>
                      {onlineRows.map((row) => (
                        <tr key={row.unit_id}>
                          <td>{row.label}</td>
                          <td>{row.session_count}</td>
                          <td>
                            <input
                              type="number"
                              min={0}
                              value={row.student_count}
                              onChange={(e) => {
                                const n = Number(e.target.value);
                                setOnlineRows((prev) =>
                                  prev.map((r) =>
                                    r.unit_id === row.unit_id
                                      ? { ...r, student_count: Number.isFinite(n) ? n : r.student_count }
                                      : r,
                                  ),
                                );
                              }}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </fieldset>
              )}
              {staffDetail && !onlineRows.length && (
                <p className="muted entity-hint">
                  No online bookings for this lecturer in the current timetable.
                </p>
              )}
              <label className="checkbox">
                <input
                  name="timetable_locked"
                  type="checkbox"
                  defaultChecked={!!selectedStaff.timetable_locked}
                />
                Timetable locked
              </label>
              {!availabilityLoading && (
                <StaffAvailabilityGrid
                  blocked={blockedSlots}
                  onChange={setBlockedSlots}
                  disabled={saving}
                />
              )}
              {availabilityLoading && <p className="muted">Loading availability…</p>}
              <button type="submit" className="btn-primary" disabled={saving}>
                {saving ? "Saving…" : "Save staff"}
              </button>
            </form>
          )}
          {selectedRoom && activeTab === "rooms" && (
            <form key={selectedRoom.id} className="form" onSubmit={save}>
              <label>
                Code
                <input name="code" defaultValue={selectedRoom.code} required />
              </label>
              <label>
                Name
                <input name="name" defaultValue={selectedRoom.name ?? ""} />
              </label>
              <label>
                Type
                <select name="room_type" defaultValue={selectedRoom.room_type ?? ""}>
                  <option value="">—</option>
                  {roomTypeChoices.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Capacity
                <input name="capacity" type="number" defaultValue={selectedRoom.capacity ?? ""} />
              </label>
              <button type="submit" className="btn-primary" disabled={saving}>
                {saving ? "Saving…" : "Save room"}
              </button>
            </form>
          )}
          {selectedUnit && activeTab === "units" && (
            <form key={selectedUnit.id} className="form" onSubmit={save}>
              <div className="row gap entity-form-actions-top">
                <button
                  type="button"
                  className="btn-secondary btn-xs"
                  disabled={saving}
                  onClick={async () => {
                    setSaving(true);
                    setError(null);
                    try {
                      const result = await api.splitUnitsFromBrackets(sessionId);
                      setMessage(`Updated ${result.updated} class(es) from names`);
                      onUpdated();
                    } catch (err) {
                      setError(err instanceof Error ? err.message : "Split failed");
                    } finally {
                      setSaving(false);
                    }
                  }}
                >
                  Split (…) from names
                </button>
              </div>
              <label>
                Name
                <input name="name" defaultValue={selectedUnit.name} required />
              </label>
              <label>
                Length (hours)
                <input
                  name="length_hours"
                  type="number"
                  step={0.5}
                  min={0}
                  defaultValue={
                    selectedUnit.length_slots ? selectedUnit.length_slots / 2 : ""
                  }
                />
              </label>
              <label>
                Component codes
                <input name="component_codes" defaultValue={selectedUnit.component_codes ?? ""} />
              </label>
              <label className="checkbox">
                <input
                  name="double_session"
                  type="checkbox"
                  checked={unitDoubleSession}
                  onChange={(e) => setUnitDoubleSession(e.target.checked)}
                />
                Double session (two bookings)
              </label>
              {unitDoubleSession && (
                <label className="checkbox">
                  <input
                    name="double_session_same_day"
                    type="checkbox"
                    defaultChecked={!!selectedUnit.double_session_same_day}
                  />
                  Same day (30 min gap between parts)
                </label>
              )}
              {unitDoubleSession && (
                <label>
                  First session (hours)
                  <input
                    name="double_session_first_hours"
                    type="number"
                    step={0.5}
                    min={0.5}
                    max={
                      selectedUnit.length_slots && selectedUnit.length_slots / 2 > 0.5
                        ? selectedUnit.length_slots / 2 - 0.5
                        : undefined
                    }
                    defaultValue={
                      selectedUnit.double_session_first_slots != null
                        ? selectedUnit.double_session_first_slots / 2
                        : selectedUnit.length_slots
                          ? selectedUnit.length_slots / 4
                          : ""
                    }
                  />
                  {selectedUnit.length_slots ? (
                    <span className="muted entity-hint">
                      Total {selectedUnit.length_slots / 2} h — second session gets the remaining hours.
                    </span>
                  ) : null}
                </label>
              )}
              {staff.length > 0 && (
                <fieldset className="qual-link-fieldset constraint-fieldset">
                  <legend>Lecturer constraints</legend>
                  <input
                    type="search"
                    placeholder="Search lecturers…"
                    value={lecturerSearch}
                    onChange={(e) => setLecturerSearch(e.target.value)}
                    className="entity-list-search"
                  />
                  {filteredStaffForUnit.map((s) => (
                    <label key={s.id} className="checkbox">
                      <input
                        type="checkbox"
                        checked={competentStaffIds.includes(s.id)}
                        onChange={(e) => {
                          setCompetentStaffIds((prev) =>
                            e.target.checked ? [...prev, s.id] : prev.filter((id) => id !== s.id),
                          );
                        }}
                      />
                      {s.name}
                    </label>
                  ))}
                </fieldset>
              )}
              {rooms.length > 0 && (
                <fieldset className="qual-link-fieldset constraint-fieldset">
                  <legend>Allowed rooms (empty = any)</legend>
                  {onCampusRoomIds.length > 0 && (
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={allOnCampusSelected}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setAllowedRoomIds((prev) => [
                              ...new Set([...prev, ...onCampusRoomIds]),
                            ]);
                          } else {
                            setAllowedRoomIds((prev) =>
                              prev.filter((id) => !onCampusRoomIds.includes(id)),
                            );
                          }
                        }}
                      />
                      All on-campus rooms
                    </label>
                  )}
                  {rooms.map((r) => (
                    <label key={r.id} className="checkbox">
                      <input
                        type="checkbox"
                        checked={allowedRoomIds.includes(r.id)}
                        onChange={(e) => {
                          setAllowedRoomIds((prev) =>
                            e.target.checked ? [...prev, r.id] : prev.filter((id) => id !== r.id),
                          );
                        }}
                      />
                      {r.code} ({roomTypeLabel(r, roomTypeChoices)})
                    </label>
                  ))}
                </fieldset>
              )}
              {qualifications.length > 0 && (
                <fieldset className="qual-link-fieldset">
                  <legend>Qualifications</legend>
                  {qualifications.map((q) => (
                    <label key={q.id} className="checkbox">
                      <input
                        type="checkbox"
                        checked={unitQualIds.includes(q.id)}
                        onChange={(e) => {
                          setUnitQualIds((prev) =>
                            e.target.checked ? [...prev, q.id] : prev.filter((id) => id !== q.id),
                          );
                        }}
                      />
                      {q.name}
                    </label>
                  ))}
                </fieldset>
              )}
              <button type="submit" className="btn-primary" disabled={saving}>
                {saving ? "Saving…" : "Save unit"}
              </button>
            </form>
          )}
          {selectedCourse && activeTab === "courses" && (
            <form key={selectedCourse.id} className="form" onSubmit={save}>
              <label>
                Code
                <input name="code" defaultValue={selectedCourse.code} required />
              </label>
              <label>
                Name
                <input name="name" defaultValue={selectedCourse.name ?? ""} />
              </label>
              <label className="checkbox">
                <input
                  name="timetable_locked"
                  type="checkbox"
                  defaultChecked={!!selectedCourse.timetable_locked}
                />
                Timetable locked
              </label>
              <button type="submit" className="btn-primary" disabled={saving}>
                {saving ? "Saving…" : "Save course"}
              </button>
            </form>
          )}
          {selectedQual && activeTab === "qualifications" && (
            <form key={selectedQual.id} className="form" onSubmit={save}>
              {qualDetail && (
                <div className="qual-detail-summary muted">
                  {qualDetail.groups_summary && <p>{qualDetail.groups_summary}</p>}
                  {qualDetail.schedule_summary && <p>{qualDetail.schedule_summary}</p>}
                  {qualDetail.block_status && <p>{qualDetail.block_status}</p>}
                </div>
              )}
              <label>
                Name
                <input name="name" defaultValue={selectedQual.name} required />
              </label>
              <label>
                Number of groups
                <input
                  name="num_groups"
                  type="number"
                  min={1}
                  max={26}
                  defaultValue={qualDetail?.num_groups ?? selectedQual.num_groups ?? 1}
                />
              </label>
              <label>
                Schedule period
                <select name="schedule_period" defaultValue={selectedQual.schedule_period ?? "day"}>
                  <option value="day">Day (08:30–19:00)</option>
                  <option value="night">Night (17:30–21:30)</option>
                </select>
              </label>
              {qualDetail && qualDetail.linked_classes.length > 0 && (
                <fieldset className="qual-link-fieldset">
                  <legend>Linked classes</legend>
                  <p className="muted entity-hint">
                    Managed in the Classes tab; listed here for reference.
                  </p>
                  <ul className="entity-linked-list">
                    {qualDetail.linked_classes.map((u) => (
                      <li key={u.id}>
                        {onNavigateToUnit ? (
                          <button
                            type="button"
                            className="entity-link-btn"
                            onClick={() => onNavigateToUnit(u.id)}
                          >
                            {u.name}
                          </button>
                        ) : (
                          u.name
                        )}
                      </li>
                    ))}
                  </ul>
                </fieldset>
              )}
              <div className="row gap">
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? "Saving…" : "Save qualification"}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={saving}
                  onClick={async () => {
                    setSaving(true);
                    setError(null);
                    setMessage(null);
                    try {
                      const result = await api.createBlock(sessionId, selectedQual.id);
                      setMessage(`Created block group ${result.course_code}`);
                      onUpdated({
                        blockCourseId: result.course_id,
                        qualificationId: selectedQual.id,
                      });
                    } catch (err) {
                      setError(err instanceof Error ? err.message : "Create block failed");
                    } finally {
                      setSaving(false);
                    }
                  }}
                >
                  Create block
                </button>
              </div>
              <p className="muted entity-hint">
                Use Create block to add an intensive block cohort for this qualification. Schedule it in
                Block delivery view.
              </p>
            </form>
          )}
          {error && <p className="error">{error}</p>}
          {message && <p className="muted">{message}</p>}
        </div>
      </div>
    </section>
  );
}

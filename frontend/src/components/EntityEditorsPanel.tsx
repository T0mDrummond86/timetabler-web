import { CSSProperties, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { nonNegIntFromInput, sanitizeNonNegIntInput } from "../lib/numericInput";
import { api, Course, Qualification, Room, Staff, Unit } from "../api";
import type { QualificationDetail, StaffHoursRow, StaffOnlineStudentRow } from "../types";
import {
  blockedApiFromSet,
  blockedSetFromApi,
  StaffAvailabilityGrid,
} from "./StaffAvailabilityGrid";
import { StaffHoursTable } from "./StaffHoursTable";
import { ClassConsolidationDialog } from "./ClassConsolidationDialog";
import { QualificationMergeDialog } from "./QualificationMergeDialog";
import { StageSplitDialog } from "./StageSplitDialog";
import { LinkedSessionImportPanel } from "./LinkedSessionImportPanel";
import { useConfirmPrompt } from "../hooks/useConfirmPrompt";
import { familyOf, groupIntoFamilies } from "../stageFamily";

type Tab = "staff" | "rooms" | "units" | "courses" | "qualifications";

const STAFF_TABLE_WIDTH_KEY = "staff-editor-table-pct";
const STAFF_TABLE_WIDTH_DEFAULT = 48;
const STAFF_TABLE_WIDTH_MIN = 28;
const STAFF_TABLE_WIDTH_MAX = 72;

function readStaffTableWidthPct(): number {
  try {
    const raw = localStorage.getItem(STAFF_TABLE_WIDTH_KEY);
    const n = raw ? Number(raw) : STAFF_TABLE_WIDTH_DEFAULT;
    if (!Number.isFinite(n)) return STAFF_TABLE_WIDTH_DEFAULT;
    return Math.min(STAFF_TABLE_WIDTH_MAX, Math.max(STAFF_TABLE_WIDTH_MIN, n));
  } catch {
    return STAFF_TABLE_WIDTH_DEFAULT;
  }
}

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
  const [stageSplitFor, setStageSplitFor] = useState<number | null>(null);
  const [mergeFor, setMergeFor] = useState<number | null>(null);
  // Bumped after a split so the open editor refetches: the split renames the
  // qualification and moves its classes without changing the selected id, so
  // nothing else would tell this panel its data went stale.
  const [qualRefresh, setQualRefresh] = useState(0);
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
  const [qualSearch, setQualSearch] = useState("");
  const [unitQualFilter, setUnitQualFilter] = useState<number | "">("");
  // Marking classes as common is a separate job from editing one, so the list
  // grows ticks and a filter of its own rather than putting it in the form.
  const [unitCommonFilter, setUnitCommonFilter] = useState<"" | "marked" | "suggested">("");
  const [commonSuggestions, setCommonSuggestions] = useState<Set<number>>(new Set());
  // Ticks show immediately and save in the background. Marking is a
  // tick-down-the-list job, so blocking the list on each round trip loses
  // ticks: a second click landing during the first save was simply dropped.
  const [markOverrides, setMarkOverrides] = useState<Map<number, boolean>>(new Map());
  const [consolidateFor, setConsolidateFor] = useState<Unit[] | null>(null);
  const [roomTypeChoices, setRoomTypeChoices] = useState<[string, string][]>([]);
  const [staffHoursRows, setStaffHoursRows] = useState<StaffHoursRow[]>([]);
  const [staffHoursLoading, setStaffHoursLoading] = useState(false);
  const [staffTableWidthPct, setStaffTableWidthPct] = useState(readStaffTableWidthPct);
  const staffLayoutRef = useRef<HTMLDivElement>(null);
  const staffResizeActiveRef = useRef(false);
  const [unitDoubleSession, setUnitDoubleSession] = useState(false);
  const { confirm, prompt, dialogs } = useConfirmPrompt();

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
    try {
      localStorage.setItem(STAFF_TABLE_WIDTH_KEY, String(staffTableWidthPct));
    } catch {
      /* ignore quota / private mode */
    }
  }, [staffTableWidthPct]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!staffResizeActiveRef.current || !staffLayoutRef.current) return;
      const rect = staffLayoutRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setStaffTableWidthPct(
        Math.min(STAFF_TABLE_WIDTH_MAX, Math.max(STAFF_TABLE_WIDTH_MIN, pct)),
      );
    };
    const onUp = () => {
      staffResizeActiveRef.current = false;
      document.body.classList.remove("staff-editor-resizing");
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const beginStaffResize = useCallback(() => {
    staffResizeActiveRef.current = true;
    document.body.classList.add("staff-editor-resizing");
  }, []);

  useEffect(() => {
    if (focusEntityId == null) return;
    if (fixedTab !== "units" && activeTab !== "units") return;
    setSelectedId(focusEntityId);
    setMessage(null);
    setError(null);
    onFocusConsumed?.();
  }, [focusEntityId, fixedTab, activeTab, onFocusConsumed]);

  // Which classes share a unit code with another. Worked out server-side rather
  // than stored, so it has to be fetched, and refetched after a consolidation
  // removes one of a pair.
  useEffect(() => {
    if (activeTab !== "units") return;
    let cancelled = false;
    void (async () => {
      try {
        const data = await api.commonClassSuggestions(sessionId);
        if (!cancelled) setCommonSuggestions(new Set(data.unit_ids));
      } catch {
        if (!cancelled) setCommonSuggestions(new Set());
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, activeTab, units]);

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
    // Clear first: the form below seeds its inputs from qualDetail, so leaving
    // the previous qualification's detail in place while the next one loads
    // would show one stage's group count against another stage's name.
    setQualDetail(null);
    if (activeTab === "qualifications" && selectedId != null) {
      let cancelled = false;
      api
        .qualificationDetail(sessionId, selectedId)
        .then((d) => {
          if (!cancelled) setQualDetail(d);
        })
        .catch(() => {
          if (!cancelled) setQualDetail(null);
        });
      return () => {
        cancelled = true;
      };
    }
  }, [sessionId, activeTab, selectedId, qualRefresh]);

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

  const qualFamilies = useMemo(() => groupIntoFamilies(qualifications), [qualifications]);

  // A split qualification is still one qualification to the user, so a family
  // is one row: selecting it opens its first stage, and `memberIds` keeps the
  // row highlighted while any of its stages is being edited.
  const baseRows: { id: number; label: string; memberIds?: number[] }[] =
    activeTab === "staff"
      ? staff.map((s) => ({ id: s.id, label: s.name }))
      : activeTab === "rooms"
        ? rooms.map((r) => ({ id: r.id, label: r.code }))
        : activeTab === "units"
          ? units.map((u) => ({ id: u.id, label: u.name }))
          : activeTab === "courses"
            ? courses.map((c) => ({ id: c.id, label: c.code }))
            : qualFamilies.map((f) => ({
                id: f.stages[0].id,
                label: f.label,
                memberIds: f.stages.map((s) => s.id),
              }));

  const isMarked = useCallback(
    (unit: Unit) => markOverrides.get(unit.id) ?? !!unit.common_class,
    [markOverrides],
  );

  const rows = useMemo(() => {
    if (activeTab === "units") {
      const q = unitSearch.trim().toLowerCase();
      return baseRows.filter((row) => {
        const unit = units.find((u) => u.id === row.id);
        if (!unit) return false;
        if (unitQualFilter !== "" && !(unit.qualification_ids ?? []).includes(unitQualFilter)) {
          return false;
        }
        if (q && !unit.name.toLowerCase().includes(q)) return false;
        if (unitCommonFilter === "marked" && !isMarked(unit)) return false;
        if (unitCommonFilter === "suggested" && !commonSuggestions.has(unit.id)) return false;
        return true;
      });
    }
    if (activeTab === "qualifications") {
      const q = qualSearch.trim().toLowerCase();
      if (!q) return baseRows;
      // Search the stage names too, so "Stg2" still finds its family.
      return baseRows.filter((row) => {
        if (row.label.toLowerCase().includes(q)) return true;
        return (row.memberIds ?? []).some((id) =>
          qualifications.find((x) => x.id === id)?.name.toLowerCase().includes(q),
        );
      });
    }
    return baseRows;
  }, [
    activeTab,
    baseRows,
    units,
    unitSearch,
    unitQualFilter,
    unitCommonFilter,
    commonSuggestions,
    isMarked,
    qualSearch,
    qualifications,
  ]);

  const markedUnits = useMemo(() => units.filter(isMarked), [units, isMarked]);

  // Drop an override once the reloaded list agrees with it, so the two cannot
  // drift if a save fails somewhere else.
  useEffect(() => {
    setMarkOverrides((prev) => {
      if (!prev.size) return prev;
      const next = new Map(prev);
      for (const unit of units) {
        if (next.get(unit.id) === !!unit.common_class) next.delete(unit.id);
      }
      return next.size === prev.size ? prev : next;
    });
  }, [units]);

  /** Tick or untick one class. Saved in the background -- there is no form to submit. */
  async function toggleCommon(unitId: number, marked: boolean) {
    setMarkOverrides((prev) => new Map(prev).set(unitId, marked));
    setError(null);
    try {
      await api.markCommonClasses(sessionId, [unitId], marked);
      onUpdated();
    } catch (err) {
      setMarkOverrides((prev) => {
        const next = new Map(prev);
        next.delete(unitId);
        return next;
      });
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  async function markSuggested() {
    const ids = [...commonSuggestions];
    if (!ids.length) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.markCommonClasses(sessionId, ids, true);
      setMessage(`Marked ${result.updated} class(es) that share a unit code.`);
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  async function clearMarks() {
    const ids = markedUnits.map((u) => u.id);
    if (!ids.length) return;
    setSaving(true);
    setError(null);
    try {
      await api.markCommonClasses(sessionId, ids, false);
      setMessage(null);
      onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

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
  const selectedFamily = familyOf(qualFamilies, selectedId);

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
          cost_centre: String(form.get("cost_centre") || "") || null,
          fte: (() => {
            const raw = form.get("fte");
            if (!raw) return null;
            const n = Number(raw);
            if (Number.isNaN(n)) return null;
            return Math.round(n * 1000) / 1000;
          })(),
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
          default_online_students_per_class: (() => {
            const raw = String(form.get("default_online_students_per_class") ?? "").trim();
            if (!raw) return null;
            return nonNegIntFromInput(raw, 0);
          })(),
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
        onUpdated();
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
          // The only real constraint is that the second session gets something:
          // a "double" whose first half is the whole class is just a single.
          // Anything up to that is allowed, so a 3-hour class can be split
          // 2.5 + 0.5 as readily as 1.5 + 1.5. Trimming to the largest legal
          // value rather than silently halving keeps the saved figure close to
          // what was typed.
          let firstSlots = Math.max(1, Math.round(firstHours * 2));
          if (firstSlots >= lengthSlots) {
            firstSlots = Math.max(1, lengthSlots - 1);
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
    const promptTitle =
      activeTab === "staff"
        ? "New staff member"
        : activeTab === "rooms"
          ? "New room"
          : activeTab === "units"
            ? "New class"
            : "New qualification";
    const placeholder =
      activeTab === "staff"
        ? "Staff name"
        : activeTab === "rooms"
          ? "Room code"
          : activeTab === "units"
            ? "Class name"
            : "Qualification name";
    const label = await prompt({ title: promptTitle, placeholder });
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

  /** Copy the selected qualification, sharing its classes rather than recreating them.
   *
   * The sharing is the point, so the prompt says it in as many words: a user
   * who expects a deep copy would otherwise go looking for the duplicated
   * classes in the Classes tab and not find them.
   */
  async function duplicateQualification() {
    if (selectedId == null) return;
    let preview: import("../types").QualificationDuplicatePreview;
    try {
      preview = await api.qualificationDuplicatePreview(sessionId, selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load");
      return;
    }
    // Named for the whole qualification, and it says how many stages are
    // coming with it: the list shows a split qualification as one row, so the
    // user never chose which stage record happens to be open.
    const stages =
      preview.stage_count > 1
        ? ` All ${preview.stage_count} stages are copied (${preview.stage_names.join(", ")}).`
        : "";
    const label = await prompt({
      title: `Duplicate ${preview.source_name}`,
      message:
        `The copy shares this qualification's ${preview.class_count} class(es) rather ` +
        `than making new ones, so editing a class changes it in both. It gets its own ` +
        `${preview.num_groups} group(s) with those classes ready to place, and starts ` +
        `with an empty timetable.${stages}`,
      defaultValue: preview.suggested_name,
      placeholder: "New qualification name",
      confirmLabel: "Duplicate",
    });
    if (!label?.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.duplicateQualification(sessionId, selectedId, label.trim());
      setMessage(result.summary);
      setQualRefresh((n) => n + 1);
      // A new qualification with new group courses — the sidebar and every
      // list of qualifications is stale until the caller reloads.
      setSelectedId(result.qualification_id);
      onUpdated({ qualificationId: result.qualification_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Duplicate failed");
    } finally {
      setSaving(false);
    }
  }

  async function deleteEntity() {
    if (selectedId == null) return;
    const row = rows.find((r) => r.id === selectedId);
    if (
      !(await confirm({
        title: "Delete item",
        message: `Delete ${row?.label ?? "this item"}? This cannot be undone.`,
        confirmLabel: "Delete",
        danger: true,
      }))
    )
      return;
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

  const layoutClass =
    activeTab === "staff"
      ? fixedTab
        ? "tt-workspace entity-editor-workspace staff-editor-layout staff-editor-resizable"
        : "entity-editor-layout staff-editor-layout staff-editor-resizable"
      : fixedTab
        ? "tt-workspace entity-editor-workspace"
        : "entity-editor-layout";

  const listColClass =
    activeTab === "staff"
      ? fixedTab
        ? "tt-sidebar entity-list-col staff-hours-list-col"
        : "entity-list-col staff-hours-list-col"
      : fixedTab
        ? "tt-sidebar entity-list-col"
        : "entity-list-col";

  const formWrapClass = fixedTab ? "tt-main entity-form-wrap" : "entity-form-wrap";

  return (
    <section className={`panel${fixedTab ? " entity-editor-panel--fill" : ""}`}>
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
        ref={activeTab === "staff" ? staffLayoutRef : undefined}
        className={layoutClass}
        style={
          activeTab === "staff"
            ? ({ ["--staff-table-col" as string]: `${staffTableWidthPct}%` } as CSSProperties)
            : undefined
        }
      >
        <div className={listColClass}>
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
              <select
                className="field-select"
                value={unitCommonFilter}
                onChange={(e) =>
                  setUnitCommonFilter(e.target.value as "" | "marked" | "suggested")
                }
                aria-label="Filter by common class"
              >
                <option value="">All classes</option>
                <option value="marked">Marked common ({markedUnits.length})</option>
                <option value="suggested">
                  Suggested ({commonSuggestions.size})
                </option>
              </select>
            </div>
          )}
          {activeTab === "units" && (
            <div className="entity-list-toolbar common-class-toolbar">
              <span className="muted common-class-count">
                {markedUnits.length} marked
              </span>
              <button
                type="button"
                className="btn-secondary btn-xs"
                disabled={saving || commonSuggestions.size === 0}
                onClick={() => void markSuggested()}
                title="Tick every class that shares a unit code with another"
              >
                Mark suggested
              </button>
              <button
                type="button"
                className="btn-secondary btn-xs"
                disabled={saving || markedUnits.length === 0}
                onClick={() => void clearMarks()}
              >
                Clear marks
              </button>
              <button
                type="button"
                className="btn-primary btn-xs"
                disabled={saving || markedUnits.length < 2}
                onClick={() => setConsolidateFor(markedUnits)}
                title={
                  markedUnits.length < 2
                    ? "Tick at least two classes to consolidate"
                    : "Fold the marked classes into one"
                }
              >
                Consolidate…
              </button>
            </div>
          )}
          {activeTab === "qualifications" && (
            <div className="entity-list-filters">
              <input
                type="search"
                className="field-input"
                placeholder="Search qualifications…"
                value={qualSearch}
                onChange={(e) => setQualSearch(e.target.value)}
                aria-label="Search qualifications"
              />
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
              {activeTab === "qualifications" && (
                <button
                  type="button"
                  className="btn-secondary btn-xs"
                  onClick={() => void duplicateQualification()}
                  disabled={saving || selectedId == null}
                  title="Copy this qualification, sharing its classes rather than recreating them"
                >
                  Duplicate
                </button>
              )}
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
                <li key={row.id} className={activeTab === "units" ? "entity-row-ticked" : undefined}>
                  {activeTab === "units" && (
                    <input
                      type="checkbox"
                      className="entity-tick"
                      checked={
                        markOverrides.get(row.id) ??
                        !!units.find((u) => u.id === row.id)?.common_class
                      }
                      onChange={(e) => void toggleCommon(row.id, e.target.checked)}
                      aria-label={`Mark ${row.label} as taught under several qualifications`}
                      title={
                        commonSuggestions.has(row.id)
                          ? "Shares a unit code with another class"
                          : "Mark as common across qualifications"
                      }
                    />
                  )}
                  <button
                    type="button"
                    className={
                      selectedId === row.id ||
                      (selectedId != null && (row.memberIds ?? []).includes(selectedId))
                        ? "entity-item active"
                        : "entity-item"
                    }
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
              {!rows.length && (
                <li className="tt-entity-empty">
                  {activeTab === "qualifications" && qualSearch.trim() && qualifications.length
                    ? "No qualifications match your search."
                    : `No ${activeTab} in this session.`}
                </li>
              )}
            </ul>
          )}
        </div>
        {activeTab === "staff" && (
          <div
            className="staff-editor-resize-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize staff table and editor"
            aria-valuemin={STAFF_TABLE_WIDTH_MIN}
            aria-valuemax={STAFF_TABLE_WIDTH_MAX}
            aria-valuenow={Math.round(staffTableWidthPct)}
            tabIndex={0}
            onMouseDown={(e) => {
              e.preventDefault();
              beginStaffResize();
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft") {
                e.preventDefault();
                setStaffTableWidthPct((p) => Math.max(STAFF_TABLE_WIDTH_MIN, p - 2));
              } else if (e.key === "ArrowRight") {
                e.preventDefault();
                setStaffTableWidthPct((p) => Math.min(STAFF_TABLE_WIDTH_MAX, p + 2));
              }
            }}
          />
        )}
        <div className={formWrapClass}>
          {selectedId == null && <p className="muted">Select an item to edit.</p>}
          {selectedStaff && activeTab === "staff" && (
            <form key={selectedStaff.id} className="form" onSubmit={save}>
              <label>
                Name
                <input name="name" defaultValue={selectedStaff.name} required />
              </label>
              <label>
                Cost centre
                <input
                  name="cost_centre"
                  defaultValue={selectedStaff.cost_centre ?? ""}
                  placeholder="e.g. 12345"
                />
              </label>
              <label>
                FTE
                <input
                  name="fte"
                  type="number"
                  step="0.001"
                  min="0"
                  defaultValue={selectedStaff.fte ?? ""}
                />
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
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  className="input-numeric-plain"
                  defaultValue={
                    selectedStaff.default_online_students_per_class != null
                      ? String(selectedStaff.default_online_students_per_class)
                      : ""
                  }
                  onChange={(e) => {
                    e.target.value = sanitizeNonNegIntInput(e.target.value);
                  }}
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
                              type="text"
                              inputMode="numeric"
                              pattern="[0-9]*"
                              className="input-numeric-plain"
                              value={row.student_count === 0 ? "0" : String(row.student_count)}
                              onChange={(e) => {
                                const digits = sanitizeNonNegIntInput(e.target.value);
                                setOnlineRows((prev) =>
                                  prev.map((r) =>
                                    r.unit_id === row.unit_id
                                      ? {
                                          ...r,
                                          student_count: nonNegIntFromInput(digits, 0),
                                        }
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
                    /* No max. It used to be derived from the *saved* length, so
                       after lengthening a class the old ceiling still applied
                       and the field refused a perfectly valid figure until the
                       class was saved and reopened. The save path trims
                       anything that would leave the second session empty. */
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
          {selectedQual && activeTab === "qualifications" && selectedFamily?.isSplit && (
            <div className="qual-stage-tabs" role="tablist" aria-label="Stages">
              {selectedFamily.stages.map((stage, i) => (
                <button
                  key={stage.id}
                  type="button"
                  role="tab"
                  aria-selected={stage.id === selectedQual.id}
                  className={
                    stage.id === selectedQual.id
                      ? "qual-stage-tab qual-stage-tab--active"
                      : "qual-stage-tab"
                  }
                  title={stage.name}
                  onClick={() => {
                    setSelectedId(stage.id);
                    setMessage(null);
                    setError(null);
                  }}
                >
                  Stage {i + 1}
                </button>
              ))}
            </div>
          )}
          {selectedQual && activeTab === "qualifications" && (
            // Keyed on the loaded detail as well as the selection, so the
            // uncontrolled inputs re-seed once the right detail arrives.
            <form
              key={`${selectedQual.id}:${qualRefresh}:${qualDetail?.id ?? "pending"}`}
              className="form"
              onSubmit={save}
            >
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
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={saving}
                  title="Split this qualification's classes into a stage each"
                  onClick={() => setStageSplitFor(selectedQual.id)}
                >
                  Stage split
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={saving}
                  title="Combine this qualification with another into a new one. Both are kept."
                  onClick={() => setMergeFor(selectedQual.id)}
                >
                  Merge
                </button>
              </div>
            </form>
          )}
          {error && <p className="error">{error}</p>}
          {message && <p className="muted">{message}</p>}
        </div>
      </div>
      {dialogs}
      {mergeFor != null && (
        <QualificationMergeDialog
          sessionId={sessionId}
          qualificationId={mergeFor}
          qualifications={qualifications}
          onClose={() => setMergeFor(null)}
          onMerge={(summary, newId) => {
            setMergeFor(null);
            setMessage(summary);
            setQualRefresh((n) => n + 1);
            // A new qualification with new group courses -- the sidebar and
            // every list of qualifications is stale until the caller reloads.
            // Select the new one, since it is what the user just made.
            setSelectedId(newId);
            onUpdated({ qualificationId: newId });
          }}
        />
      )}
      {consolidateFor && consolidateFor.length > 1 && (
        <ClassConsolidationDialog
          sessionId={sessionId}
          units={consolidateFor}
          onClose={() => setConsolidateFor(null)}
          onConsolidated={(summary, survivorId) => {
            setConsolidateFor(null);
            setMessage(summary);
            // Classes were deleted and placecards repointed -- the grid, the
            // sidebar and every class list are stale until the caller reloads.
            setSelectedId(survivorId);
            onUpdated();
          }}
        />
      )}
      {stageSplitFor != null && (
        <StageSplitDialog
          sessionId={sessionId}
          qualificationId={stageSplitFor}
          onClose={() => setStageSplitFor(null)}
          onSplit={(summary) => {
            setStageSplitFor(null);
            setMessage(summary);
            setQualRefresh((n) => n + 1);
            // Stages are new qualifications with new courses — the sidebar and
            // every list of qualifications is stale until the caller reloads.
            onUpdated({ qualificationId: stageSplitFor });
          }}
        />
      )}
    </section>
  );
}

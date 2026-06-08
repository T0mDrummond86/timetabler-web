"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: int | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    name: str

    model_config = {"from_attributes": True}


class OrganizationOut(BaseModel):
    id: int
    name: str
    slug: str
    role: str

    model_config = {"from_attributes": True}


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TimetableSessionOut(BaseModel):
    id: int
    organization_id: int
    name: str
    created_at: datetime
    updated_at: datetime
    global_session_id: int | None = None
    global_session_name: str | None = None
    course_count: int = 0
    booking_count: int = 0

    model_config = {"from_attributes": True}


class TimetableSessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, default="Default")


class TimetableSessionPatch(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TimetableSessionDuplicate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TimetableSessionLinkOut(BaseModel):
    id: int
    name: str


class GlobalSessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class GlobalSessionSummaryOut(BaseModel):
    id: int
    organization_id: int
    name: str
    member_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GlobalSessionOut(BaseModel):
    id: int
    organization_id: int
    name: str
    created_at: datetime
    updated_at: datetime
    member_sessions: list[TimetableSessionLinkOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class GlobalSessionMembersPatch(BaseModel):
    timetable_session_ids: list[int] = Field(default_factory=list)


class LinkedImportStaffOptionOut(BaseModel):
    id: int
    name: str
    already_in_target: bool = False


class LinkedImportQualOptionOut(BaseModel):
    id: int
    name: str
    linked_classes: list[str] = Field(default_factory=list)
    already_in_target: bool = False


class LinkedImportOptionsOut(BaseModel):
    staff: list[LinkedImportStaffOptionOut] = Field(default_factory=list)
    qualifications: list[LinkedImportQualOptionOut] = Field(default_factory=list)


class LinkedSessionImportIn(BaseModel):
    source_session_id: int
    staff_ids: list[int] = Field(default_factory=list)
    qualification_ids: list[int] = Field(default_factory=list)


class LinkedImportResultOut(BaseModel):
    added: list[str] = Field(default_factory=list)
    classes_added: list[str] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)


class LinkedSessionImportOut(BaseModel):
    staff: LinkedImportResultOut | None = None
    qualifications: LinkedImportResultOut | None = None


class CourseOut(BaseModel):
    id: int
    code: str
    name: str | None = None
    timetable_locked: int = 0

    model_config = {"from_attributes": True}


class ViolationOut(BaseModel):
    severity: str
    code: str
    message: str
    booking_ids: list[int] = Field(default_factory=list)


class BookingCardOut(BaseModel):
    id: int
    course_id: int | None = None
    day: int
    column: int | None = None
    start_slot: int
    end_slot: int
    lane: int
    lane_depth: int
    unit_name: str | None
    course_code: str | None
    staff_name: str | None
    room_code: str | None
    room_id: int | None = None
    notes: str | None
    external_id: str | None
    colour_key: str
    fill_colour: str
    border_colour: str
    is_hard: bool
    is_soft: bool
    lock_time: bool = False
    lock_staff: bool = False
    in_term_1: bool = True
    in_term_2: bool = True
    unit_id: int | None = None
    session_part: int = 1
    sfs_co_teacher_staff_id: int | None = None
    sfs_co_teacher_name: str | None = None
    sfs_co_teacher_in_term_1: bool = False
    sfs_co_teacher_in_term_2: bool = False
    online_student_count: int | None = None
    room_is_online: bool = False
    violations: list[ViolationOut]


class TimetableGridOut(BaseModel):
    timetable_session_id: int
    view: str = "course"
    entity_id: int
    entity_label: str
    course_id: int | None = None
    course_code: str | None = None
    week_id: int
    week_label: str
    column_kind: str = "day"
    focus_day: int | None = None
    columns: list[str] = Field(default_factory=list)
    days: list[str]
    num_slots: int
    slot_minutes: int
    first_slot_time: str
    bookings: list[BookingCardOut]
    violations: list[ViolationOut]
    semester_week: int | None = None
    block_week_index: int | None = None
    readonly: bool = False
    schedule_variants: list[dict] = Field(default_factory=list)
    preview_semester_week: int | None = None
    unavailable_slots: dict[str, list[int]] | None = None
    linked_session_busy_slots: dict[str, list[int]] | None = None
    linked_session_busy_label: str | None = None
    staff_hours: float | None = None


class TimetableEntityOut(BaseModel):
    id: int
    label: str
    entity_type: str


class SemesterWeekCellOut(BaseModel):
    week: int
    active: bool
    applicable: bool
    booking_id: int


class SemesterScheduleRowOut(BaseModel):
    primary_booking_id: int
    label: str
    has_variants: bool
    weeks: list[SemesterWeekCellOut]


class CourseSemesterScheduleOut(BaseModel):
    course_id: int
    course_code: str
    selected_semester_week: int
    semester_weeks: int
    rows: list[SemesterScheduleRowOut]


class BlockGroupOut(BaseModel):
    id: int
    code: str


class BlockDeliveryPanelOut(BaseModel):
    qualification_id: int
    qualification_name: str
    groups: list[BlockGroupOut]
    selected_course_id: int | None = None
    block_week_count: int = 1
    block_start_semester_week: int = 1
    block_week_index: int = 1
    summary: str = ""


class BlockOverviewRowOut(BaseModel):
    course_id: int
    label: str
    tooltip: str
    calendar_weeks: list[int]


class BlockOverviewOut(BaseModel):
    rows: list[BlockOverviewRowOut]
    semester_weeks: int


class BlockWeekUsageCellOut(BaseModel):
    status: str
    label: str
    tooltip: str


class BlockWeekUsageOut(BaseModel):
    title: str
    subtitle: str
    rooms: list[str]
    days: list[str]
    cells: list[list[BlockWeekUsageCellOut]]


class SessionWeekToggleRequest(BaseModel):
    booking_id: int
    semester_week: int = Field(ge=1, le=20)


class ScheduleVariantOut(BaseModel):
    label: str
    preview_week: int


class ViolationsReportOut(BaseModel):
    summary: str
    headers: list[str]
    rows: list[dict]


class SidebarOrderRequest(BaseModel):
    view: str = Field(pattern="^(course|staff)$")
    entity_ids: list[int]


class BlockGroupDuplicateRequest(BaseModel):
    new_code: str = Field(min_length=1, max_length=120)


class BlockGroupPatch(BaseModel):
    block_week_count: int | None = Field(default=None, ge=1, le=3)
    block_start_semester_week: int | None = Field(default=None, ge=1, le=20)


class StaffOut(BaseModel):
    id: int
    name: str
    max_hours_per_week: float | None = None
    fte: float | None = None
    non_teaching_day: int | None = None
    ot_hours: float | None = None
    development_project_hours: float | None = None
    development_project_description: str | None = None
    tae_hours: float | None = None
    supervision_hours: float | None = None
    default_online_students_per_class: int | None = None
    timetable_locked: int = 0

    model_config = {"from_attributes": True}


class StaffPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    max_hours_per_week: float | None = None
    fte: float | None = None
    non_teaching_day: int | None = Field(default=None, ge=0, le=4)
    ot_hours: float | None = None
    development_project_hours: float | None = None
    development_project_description: str | None = None
    tae_hours: float | None = None
    supervision_hours: float | None = None
    default_online_students_per_class: int | None = Field(default=None, ge=0)
    timetable_locked: int | None = Field(default=None, ge=0, le=1)


class RoomOut(BaseModel):
    id: int
    code: str
    name: str | None = None
    room_type: str | None = None
    capacity: int | None = None

    model_config = {"from_attributes": True}


class RoomPatch(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = None
    room_type: str | None = None
    capacity: int | None = Field(default=None, ge=0)


class BookingPatchRequest(BaseModel):
    course_id: int
    day: int | None = Field(default=None, ge=0, le=4)
    start_slot: int | None = Field(default=None, ge=0, le=27)
    end_slot: int | None = Field(default=None, ge=1, le=28)
    notes: str | None = None
    staff_id: int | None = None
    room_id: int | None = None
    lock_time: int | None = Field(default=None, ge=0, le=1)
    lock_staff: int | None = Field(default=None, ge=0, le=1)
    unit_id: int | None = None
    external_id: str | None = None
    in_term_1: int | None = Field(default=None, ge=0, le=1)
    in_term_2: int | None = Field(default=None, ge=0, le=1)
    sfs_co_teacher_staff_id: int | None = None
    sfs_co_teacher_in_term_1: int | None = Field(default=None, ge=0, le=1)
    sfs_co_teacher_in_term_2: int | None = Field(default=None, ge=0, le=1)
    online_student_count: int | None = Field(default=None, ge=0)

    @property
    def move_only(self) -> bool:
        return (
            self.day is not None
            and self.start_slot is not None
            and self.end_slot is None
            and self.notes is None
            and self.staff_id is None
            and self.room_id is None
            and self.lock_time is None
            and self.lock_staff is None
            and self.unit_id is None
            and self.external_id is None
            and self.in_term_1 is None
            and self.in_term_2 is None
            and self.sfs_co_teacher_staff_id is None
            and self.sfs_co_teacher_in_term_1 is None
            and self.sfs_co_teacher_in_term_2 is None
            and self.online_student_count is None
        )


class BookingChangeOut(BaseModel):
    description: str
    before: dict[str, dict | None]
    after: dict[str, dict | None]


class BookingRestoreRequest(BaseModel):
    course_id: int
    action: str = Field(pattern="^(undo|redo)$")
    label: str = Field(min_length=1, max_length=200)
    snapshots: dict[str, dict | None]


class BookingMutationOut(BaseModel):
    grid: TimetableGridOut
    change: BookingChangeOut


class BookingCreateRequest(BaseModel):
    course_id: int
    unit_id: int
    day: int = Field(ge=0, le=4)
    start_slot: int = Field(ge=0, le=27)
    end_slot: int = Field(ge=1, le=28)
    staff_id: int | None = None
    room_id: int | None = None
    session_part: int = Field(default=1, ge=1, le=2)
    notes: str | None = None
    block_week_index: int | None = Field(default=None, ge=1, le=3)


class HoldingClassOut(BaseModel):
    course_id: int
    unit_id: int
    unit_name: str | None
    duration_slots: int
    session_part: int


class ImportReportOut(BaseModel):
    qualifications: int = 0
    courses: int = 0
    staff: int = 0
    rooms: int = 0
    bookings: int = 0
    source: str = ""


class SessionBackupOut(BaseModel):
    version: int
    qualifications: list[dict] = Field(default_factory=list)
    qualification_time_windows: list[dict] = Field(default_factory=list)
    courses: list[dict] = Field(default_factory=list)
    units: list[dict] = Field(default_factory=list)
    unit_qualifications: list[dict] = Field(default_factory=list)
    unit_allowed_rooms: list[dict] = Field(default_factory=list)
    course_units: list[dict] = Field(default_factory=list)
    staff: list[dict] = Field(default_factory=list)
    staff_qualification_online_students: list[dict] = Field(default_factory=list)
    staff_unit_online_students: list[dict] = Field(default_factory=list)
    staff_preferences: list[dict] = Field(default_factory=list)
    staff_competencies: list[dict] = Field(default_factory=list)
    staff_availability: list[dict] = Field(default_factory=list)
    rooms: list[dict] = Field(default_factory=list)
    bookings: list[dict] = Field(default_factory=list)


class UnitOut(BaseModel):
    id: int
    name: str
    length_slots: int | None = None
    component_codes: str | None = None
    double_session: int = 0
    double_session_same_day: int | None = None
    double_session_first_slots: int | None = None
    qualification_ids: list[int] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class UnitPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    length_slots: int | None = Field(default=None, ge=1, le=28)
    component_codes: str | None = None
    double_session: int | None = Field(default=None, ge=0, le=1)
    double_session_same_day: int | None = Field(default=None, ge=0, le=1)
    double_session_first_slots: int | None = Field(default=None, ge=1, le=27)


class UnitQualificationsPatch(BaseModel):
    qualification_ids: list[int] = Field(default_factory=list)


class QualificationGroupOut(BaseModel):
    id: int
    code: str


class QualificationLinkedClassOut(BaseModel):
    id: int
    name: str


class QualificationDetailOut(BaseModel):
    id: int
    name: str
    num_groups: int
    schedule_period: str
    delivery_mode: str
    groups_summary: str
    schedule_summary: str
    block_status: str
    regular_groups: list[QualificationGroupOut] = Field(default_factory=list)
    block_groups: list[QualificationGroupOut] = Field(default_factory=list)
    linked_classes: list[QualificationLinkedClassOut] = Field(default_factory=list)


class QualificationOut(BaseModel):
    id: int
    name: str
    num_groups: int = 1
    schedule_period: str = "day"

    model_config = {"from_attributes": True}


class QualificationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    num_groups: int | None = Field(default=None, ge=1, le=20)
    schedule_period: str | None = Field(default=None, pattern="^(day|night)$")


class CourseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=120)
    name: str | None = None
    qualification_id: int | None = None


class CourseDuplicateRequest(BaseModel):
    new_code: str = Field(min_length=1, max_length=120)


class StaffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class RoomCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)


class UnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)


class QualificationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    schedule_period: str = Field(default="day", pattern="^(day|night)$")


class CoursePatch(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = None
    timetable_locked: int | None = Field(default=None, ge=0, le=1)
    block_week_count: int | None = Field(default=None, ge=1, le=3)
    block_start_semester_week: int | None = Field(default=None, ge=1, le=20)


class ChangeLogRowDataOut(BaseModel):
    id: str = ""
    group: str = ""
    class_: str = Field(default="", alias="class")
    lecturer_change: str = ""
    time_change: str = ""
    day_change: str = ""
    room_change: str = ""
    delete: str = ""

    model_config = {"populate_by_name": True}


class ChangeLogRowOut(BaseModel):
    when: str | None = None
    action: str
    booking_id: int | None = None
    entry_id: int | None = None
    note: str = ""
    row: dict[str, str]


class ChangeLogListOut(BaseModel):
    mode: str
    rows: list[ChangeLogRowOut]


class ChangeLogNotePatch(BaseModel):
    booking_id: int
    note: str = ""


class ChangeLogRollbackRequest(BaseModel):
    booking_id: int


class AlternatePlacementOptionOut(BaseModel):
    day: int
    start_slot: int
    end_slot: int
    time_label: str
    room_id: int | None
    room_code: str
    staff_id: int | None
    is_current: bool


class AlternateSlotGroupOut(BaseModel):
    start_slot: int
    time_label: str
    options: list[AlternatePlacementOptionOut]


class AlternateDayOut(BaseModel):
    day: int
    day_label: str
    is_current_day: bool
    slots: list[AlternateSlotGroupOut]


class AvailableRoomOut(BaseModel):
    room_id: int
    room_code: str
    is_current: bool


class AlternateSlotsOut(BaseModel):
    days: list[AlternateDayOut]
    available_rooms: list[AvailableRoomOut]


class ClassCustodianRowOut(BaseModel):
    unit_id: int
    unit_name: str
    qualifications: str = "—"
    lecturers: str
    custodian: str
    custodian_deliveries: int
    unassigned_deliveries: int


class ClassCustodiansOut(BaseModel):
    summary: str
    rows: list[ClassCustodianRowOut]


class BlockedSlotOut(BaseModel):
    day: int
    slot: int


class StaffAvailabilityOut(BaseModel):
    blocked: list[BlockedSlotOut]


class StaffAvailabilityPatch(BaseModel):
    blocked: list[BlockedSlotOut]


class UsageCellOut(BaseModel):
    booking_id: int | None = None
    label: str = ""
    fill_colour: str = ""
    status: str = "free"
    tooltip: str = ""
    row_span: int = 0


class ResourceUsageOut(BaseModel):
    kind: str
    resources: list[str]
    resource_ids: list[int]
    resource_tooltips: list[str]
    days: list[str]
    num_slots: int
    cells: list[list[list[UsageCellOut]]]
    summary: str
    course_id: int | None = None


class StaffHoursRowOut(BaseModel):
    id: int
    name: str
    fte: float | None = None
    lecturing_hours: float | None = None
    in_class_timetabled_hours: float | None = None
    session_schedule_avg: str | None = None
    variance: float | None = None
    variance_category: str
    bulk_online_detail: str | None = None
    bulk_online_hours_avg: float | None = None
    development_project_hours: float | None = None
    development_project_description: str | None = None
    tae_hours: float | None = None
    supervision_hours: float | None = None
    total_hours: float
    non_teaching_day: int | None = None
    preferences_first: str = ""
    preferences_second: str = ""
    preferences_third: str = ""


class StaffPreferencesPatch(BaseModel):
    first: list[str] = Field(default_factory=list)
    second: list[str] = Field(default_factory=list)
    third: list[str] = Field(default_factory=list)


class StaffOnlineStudentPatch(BaseModel):
    unit_id: int
    student_count: int | None = None


class StaffOnlineStudentsPatch(BaseModel):
    counts: list[StaffOnlineStudentPatch] = Field(default_factory=list)


class StaffDetailOut(BaseModel):
    id: int
    name: str
    fte: float | None = None
    max_hours_per_week: float | None = None
    non_teaching_day: int | None = None
    ot_hours: float | None = None
    development_project_hours: float | None = None
    development_project_description: str | None = None
    tae_hours: float | None = None
    supervision_hours: float | None = None
    default_online_students_per_class: int | None = None
    timetable_locked: int = 0
    lecturing_hours: float | None = None
    in_class_timetabled_hours: float | None = None
    session_schedule_avg: str | None = None
    variance: float | None = None
    variance_category: str | None = None
    bulk_online_detail: str | None = None
    bulk_online_hours_avg: float | None = None
    total_hours: float | None = None
    preferences: dict[str, list[str]]
    online_students: list[dict]


class UnitConstraintsOut(BaseModel):
    unit_id: int
    allowed_room_ids: list[int]
    competent_staff_ids: list[int] = Field(default_factory=list)


class UnitAllowedRoomsPatch(BaseModel):
    room_ids: list[int]


class UnitCompetenciesPatch(BaseModel):
    staff_ids: list[int] = Field(default_factory=list)


class StaffCompetenciesPatch(BaseModel):
    unit_ids: list[int]


class ViolationDismissRequest(BaseModel):
    booking_id: int
    code: str = Field(min_length=1, max_length=80)


class RoomTypeChoicesOut(BaseModel):
    choices: list[tuple[str, str]]


class TimetablePrintEntityOut(BaseModel):
    id: int
    label: str


class TimetablePrintInfoOut(BaseModel):
    week_label: str | None
    entities: list[TimetablePrintEntityOut]


class TimetablePrintEntityIn(BaseModel):
    id: int
    label: str = Field(min_length=1, max_length=200)


class TimetablePrintRequest(BaseModel):
    kind: str = Field(pattern="^(course|staff|room)$")
    term_filter: str = Field(default="all", pattern="^(all|t1|t2)$")
    colour_by_class: bool = True
    include_index: bool = True
    entities: list[TimetablePrintEntityIn] = Field(min_length=1)

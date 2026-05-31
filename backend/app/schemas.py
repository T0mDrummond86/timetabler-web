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

    model_config = {"from_attributes": True}


class TimetableSessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, default="Default")


class CourseOut(BaseModel):
    id: int
    code: str
    name: str | None = None

    model_config = {"from_attributes": True}


class ViolationOut(BaseModel):
    severity: str
    code: str
    message: str
    booking_ids: list[int] = Field(default_factory=list)


class BookingCardOut(BaseModel):
    id: int
    day: int
    start_slot: int
    end_slot: int
    lane: int
    lane_depth: int
    unit_name: str | None
    course_code: str | None
    staff_name: str | None
    room_code: str | None
    notes: str | None
    external_id: str | None
    colour_key: str
    fill_colour: str
    border_colour: str
    is_hard: bool
    is_soft: bool
    violations: list[ViolationOut]


class TimetableGridOut(BaseModel):
    timetable_session_id: int
    course_id: int
    course_code: str
    week_id: int
    week_label: str
    days: list[str]
    num_slots: int
    slot_minutes: int
    first_slot_time: str
    bookings: list[BookingCardOut]
    violations: list[ViolationOut]

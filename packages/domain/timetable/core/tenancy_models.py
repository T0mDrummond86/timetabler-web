"""Multi-tenant auth and timetable session containers (web app)."""
from __future__ import annotations

import datetime as _dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Base


class Organization(Base):
    __tablename__ = "organization"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime,
        default=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
    )

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    timetable_sessions: Mapped[list["TimetableSession"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    global_sessions: Mapped[list["GlobalSession"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "user_account"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(200), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime,
        default=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
    )

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    global_session_access: Mapped[list["GlobalSessionUserAccess"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="GlobalSessionUserAccess.user_id"
    )


class Membership(Base):
    __tablename__ = "membership"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(20), default="editor")

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="membership_user_org_uk"),
    )


class ViolationDismissal(Base):
    """User-dismissed constraint on a booking (session-scoped, web persistence)."""

    __tablename__ = "violation_dismissal"
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_session_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_session.id", ondelete="CASCADE"),
        index=True,
    )
    booking_id: Mapped[int] = mapped_column(Integer, index=True)
    code: Mapped[str] = mapped_column(String(80))

    __table_args__ = (
        UniqueConstraint(
            "timetable_session_id",
            "booking_id",
            "code",
            name="violation_dismissal_session_booking_code_uk",
        ),
    )


class GlobalSession(Base):
    """Groups multiple timetable sessions for shared staff visibility (no timetable of its own)."""

    __tablename__ = "global_session"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime,
        default=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime,
        default=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
        onupdate=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
    )

    organization: Mapped[Organization] = relationship(back_populates="global_sessions")
    members: Mapped[list["GlobalSessionMember"]] = relationship(
        back_populates="global_session", cascade="all, delete-orphan"
    )
    user_access: Mapped[list["GlobalSessionUserAccess"]] = relationship(
        back_populates="global_session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="global_session_org_name_uk"),
    )


class GlobalSessionUserAccess(Base):
    """Grants a user access to view and use a global workspace."""

    __tablename__ = "global_session_user_access"
    id: Mapped[int] = mapped_column(primary_key=True)
    global_session_id: Mapped[int] = mapped_column(
        ForeignKey("global_session.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), index=True
    )
    granted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[_dt.datetime] = mapped_column(
        DateTime,
        default=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
    )

    global_session: Mapped[GlobalSession] = relationship(back_populates="user_access")
    user: Mapped[User] = relationship(
        back_populates="global_session_access", foreign_keys=[user_id]
    )

    __table_args__ = (
        UniqueConstraint("global_session_id", "user_id", name="global_session_user_access_uk"),
    )


class GlobalSessionMember(Base):
    """Links one timetable session into a global session."""

    __tablename__ = "global_session_member"
    id: Mapped[int] = mapped_column(primary_key=True)
    global_session_id: Mapped[int] = mapped_column(
        ForeignKey("global_session.id", ondelete="CASCADE"), index=True
    )
    timetable_session_id: Mapped[int] = mapped_column(
        ForeignKey("timetable_session.id", ondelete="CASCADE"), unique=True
    )

    global_session: Mapped[GlobalSession] = relationship(back_populates="members")
    timetable_session: Mapped["TimetableSession"] = relationship(back_populates="global_membership")


class TimetableSession(Base):
    """One editable timetable dataset within an organization (desktop ``*.db`` equivalent)."""

    __tablename__ = "timetable_session"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120))
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime,
        default=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime,
        default=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
        onupdate=lambda: _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None),
    )
    clash_check_settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="timetable_sessions")
    global_membership: Mapped[GlobalSessionMember | None] = relationship(
        back_populates="timetable_session", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="timetable_session_org_name_uk"),
    )

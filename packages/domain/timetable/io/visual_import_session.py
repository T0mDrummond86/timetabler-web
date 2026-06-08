"""Scope visual grid imports to a web timetable session (multi-tenant Postgres)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Query, Session

from ..core.models import Course, Qualification, Room, Semester, Staff, Unit, Week


@dataclass(frozen=True)
class VisualImportContext:
    """Optional session scoping for ``import_*_visual`` (web only)."""

    timetable_session_id: int | None = None

    def first_week(self, session: Session) -> Week:
        if self.timetable_session_id is None:
            week = session.query(Week).order_by(Week.id).first()
        else:
            week = (
                session.query(Week)
                .join(Semester, Semester.id == Week.semester_id)
                .filter(Semester.timetable_session_id == self.timetable_session_id)
                .order_by(Semester.id, Week.week_number)
                .first()
            )
        if week is None:
            raise RuntimeError("No week in session.")
        return week

    def _scoped(self, query: Query, model: type) -> Query:
        sid = self.timetable_session_id
        if sid is not None and hasattr(model, "timetable_session_id"):
            return query.filter(model.timetable_session_id == sid)
        return query

    def course_by_code(self, session: Session, code: str) -> Course | None:
        q = session.query(Course).filter(Course.code == code)
        return self._scoped(q, Course).one_or_none()

    def new_course(self, code: str) -> Course:
        kw: dict = {"code": code}
        if self.timetable_session_id is not None:
            kw["timetable_session_id"] = self.timetable_session_id
        return Course(**kw)

    def staff_by_name(self, session: Session, name: str) -> Staff | None:
        q = session.query(Staff).filter(Staff.name == name)
        return self._scoped(q, Staff).one_or_none()

    def new_staff(self, name: str) -> Staff:
        kw: dict = {"name": name, "max_hours_per_week": 30.0}
        if self.timetable_session_id is not None:
            kw["timetable_session_id"] = self.timetable_session_id
        return Staff(**kw)

    def room_by_code(self, session: Session, code: str) -> Room | None:
        q = session.query(Room).filter(Room.code == code)
        return self._scoped(q, Room).one_or_none()

    def new_room(self, code: str, *, room_type: str) -> Room:
        kw: dict = {"code": code, "room_type": room_type}
        if self.timetable_session_id is not None:
            kw["timetable_session_id"] = self.timetable_session_id
        return Room(**kw)

    def unit_by_name(self, session: Session, name: str) -> Unit | None:
        q = session.query(Unit).filter(Unit.name == name)
        return self._scoped(q, Unit).one_or_none()

    def new_unit(
        self,
        name: str,
        *,
        length_slots: int,
        component_codes: str | None = None,
    ) -> Unit:
        kw: dict = {
            "name": name,
            "length_slots": length_slots,
            "component_codes": component_codes,
        }
        if self.timetable_session_id is not None:
            kw["timetable_session_id"] = self.timetable_session_id
        return Unit(**kw)

    def qualification_by_name(self, session: Session, name: str) -> Qualification | None:
        q = session.query(Qualification).filter(Qualification.name == name)
        return self._scoped(q, Qualification).one_or_none()

    def new_qualification(self, **kwargs) -> Qualification:
        kw = dict(kwargs)
        if self.timetable_session_id is not None:
            kw["timetable_session_id"] = self.timetable_session_id
        return Qualification(**kw)

"""Rename cover qualification_name -> group_name on cover_log_entry and cover_request.

Lecturer cover now captures the class's *group* (the course code shown in the
courses timetable view) instead of its qualification. The column is renamed in
place so existing rows keep their stored value.
"""

from alembic import op
from sqlalchemy import inspect

revision = "016_cover_group_rename"
down_revision = "015_booking_manual_merge"
branch_labels = None
depends_on = None

_TABLES = ("cover_log_entry", "cover_request")


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    for table in _TABLES:
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "qualification_name" in cols and "group_name" not in cols:
            op.alter_column(table, "qualification_name", new_column_name="group_name")


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    for table in _TABLES:
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "group_name" in cols and "qualification_name" not in cols:
            op.alter_column(table, "group_name", new_column_name="qualification_name")

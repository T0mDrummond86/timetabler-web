"""Pending lecturer-cover requests staged per timetable session."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "014_cover_request"
down_revision = "013_cover_log_qualification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if inspector.has_table("cover_request"):
        return
    op.create_table(
        "cover_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timetable_session_id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("cover_date", sa.Date(), nullable=True),
        sa.Column("semester", sa.Integer(), nullable=True),
        sa.Column("week_number", sa.Integer(), nullable=True),
        sa.Column("day_label", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("time_label", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("qualification_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("unit_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("room_code", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("away_staff_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("cover_staff_id", sa.Integer(), nullable=True),
        sa.Column("cover_staff_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["timetable_session_id"], ["timetable_session.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_cover_request_timetable_session_id", "cover_request", ["timetable_session_id"]
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("cover_request"):
        return
    op.drop_index("ix_cover_request_timetable_session_id", table_name="cover_request")
    op.drop_table("cover_request")

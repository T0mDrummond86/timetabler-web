"""Cover log entries for one-off lecturer cover, scoped to a global session."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "011_cover_log_entry"
down_revision = "010_booking_cover_staff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if inspector.has_table("cover_log_entry"):
        return
    op.create_table(
        "cover_log_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("global_session_id", sa.Integer(), nullable=False),
        sa.Column("cover_date", sa.Date(), nullable=False),
        sa.Column("day_label", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("time_label", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("unit_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("room_code", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("away_staff_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("cover_staff_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("source_session_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["global_session_id"], ["global_session.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_cover_log_entry_global_session_id", "cover_log_entry", ["global_session_id"]
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("cover_log_entry"):
        return
    op.drop_index("ix_cover_log_entry_global_session_id", table_name="cover_log_entry")
    op.drop_table("cover_log_entry")

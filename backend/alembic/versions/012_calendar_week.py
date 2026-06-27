"""Academic calendar weeks, scoped to a global session."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "012_calendar_week"
down_revision = "011_cover_log_entry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if inspector.has_table("calendar_week"):
        return
    op.create_table(
        "calendar_week",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("global_session_id", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("monday_date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["global_session_id"], ["global_session.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "global_session_id", "semester", "week_number", name="calendar_week_uk"
        ),
    )
    op.create_index(
        "ix_calendar_week_global_session_id", "calendar_week", ["global_session_id"]
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("calendar_week"):
        return
    op.drop_index("ix_calendar_week_global_session_id", table_name="calendar_week")
    op.drop_table("calendar_week")

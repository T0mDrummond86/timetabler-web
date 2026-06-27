"""Add qualification_name to cover_log_entry."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "013_cover_log_qualification"
down_revision = "012_calendar_week"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("cover_log_entry")}
    if "qualification_name" not in cols:
        op.add_column(
            "cover_log_entry",
            sa.Column(
                "qualification_name",
                sa.String(length=300),
                nullable=False,
                server_default="",
            ),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("cover_log_entry")}
    if "qualification_name" in cols:
        op.drop_column("cover_log_entry", "qualification_name")

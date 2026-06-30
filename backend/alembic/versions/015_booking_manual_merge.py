"""Booking manual_merge_group_id for user-merged clashing classes."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "015_booking_manual_merge"
down_revision = "014_cover_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("booking")}
    if "manual_merge_group_id" not in cols:
        op.add_column(
            "booking", sa.Column("manual_merge_group_id", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("booking")}
    if "manual_merge_group_id" in cols:
        op.drop_column("booking", "manual_merge_group_id")

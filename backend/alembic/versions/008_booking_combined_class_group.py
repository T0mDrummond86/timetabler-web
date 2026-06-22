"""Booking combined_class_group_id for joint cohort delivery."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "008_booking_combined_class_group"
down_revision = "007_must_change_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("booking")}
    if "combined_class_group_id" not in cols:
        op.add_column(
            "booking",
            sa.Column("combined_class_group_id", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("booking")}
    if "combined_class_group_id" in cols:
        op.drop_column("booking", "combined_class_group_id")

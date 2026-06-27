"""Booking cover_staff_id for lecturer cover assignments."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "010_booking_cover_staff"
down_revision = "009_staff_identifier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("booking")}
    if "cover_staff_id" not in cols:
        op.add_column(
            "booking",
            sa.Column("cover_staff_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "booking_cover_staff_id_fkey",
            "booking",
            "staff",
            ["cover_staff_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("booking")}
    if "cover_staff_id" in cols:
        op.drop_constraint("booking_cover_staff_id_fkey", "booking", type_="foreignkey")
        op.drop_column("booking", "cover_staff_id")

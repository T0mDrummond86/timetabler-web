"""Add staff.staff_identifier for user-entered Staff ID."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "009_staff_identifier"
down_revision = "008_booking_combined_class_group"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("staff")}
    if "staff_identifier" not in columns:
        op.add_column("staff", sa.Column("staff_identifier", sa.String(length=80), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("staff")}
    if "staff_identifier" in columns:
        op.drop_column("staff", "staff_identifier")

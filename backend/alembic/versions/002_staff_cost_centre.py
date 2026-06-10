"""Add staff.cost_centre column."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "002_staff_cost_centre"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("staff")}
    if "cost_centre" not in columns:
        op.add_column("staff", sa.Column("cost_centre", sa.String(length=80), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in inspect(bind).get_columns("staff")}
    if "cost_centre" in columns:
        op.drop_column("staff", "cost_centre")

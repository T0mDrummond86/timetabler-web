"""Add staff.cost_centre column."""

from alembic import op
import sqlalchemy as sa

revision = "002_staff_cost_centre"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("staff", sa.Column("cost_centre", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("staff", "cost_centre")

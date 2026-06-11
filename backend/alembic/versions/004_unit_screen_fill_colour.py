"""Add unit.screen_fill_colour for manual class placecard colours."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "004_unit_screen_fill_colour"
down_revision = "003_unit_lap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("unit")}
    if "screen_fill_colour" not in cols:
        op.add_column("unit", sa.Column("screen_fill_colour", sa.String(length=7), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("unit")}
    if "screen_fill_colour" in cols:
        op.drop_column("unit", "screen_fill_colour")

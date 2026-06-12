"""Per-session clash check enable/disable settings."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "005_clash_check_settings"
down_revision = "004_unit_screen_fill_colour"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("timetable_session")}
    if "clash_check_settings_json" not in cols:
        op.add_column(
            "timetable_session",
            sa.Column("clash_check_settings_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("timetable_session")}
    if "clash_check_settings_json" in cols:
        op.drop_column("timetable_session", "clash_check_settings_json")

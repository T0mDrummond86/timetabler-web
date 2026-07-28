"""Per-session delivery mode and grid day window.

``timetable_mode`` decides which timetable views a session offers:
"hybrid" keeps the regular/block selector (today's behaviour, and the default
so nothing changes for existing sessions), while "regular" and "block" pin the
session to one family of views and drop the selector entirely.

``grid_start_slot`` / ``grid_end_slot`` narrow the displayed teaching day from
the full 08:00-22:00 span, so grids are denser on screen and on a phone.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "019_session_settings"
down_revision = "018_global_session_owner"
branch_labels = None
depends_on = None

_COLUMNS = {
    "timetable_mode": sa.Column(
        "timetable_mode", sa.String(length=16), nullable=False, server_default="hybrid"
    ),
    "grid_start_slot": sa.Column("grid_start_slot", sa.Integer(), nullable=True),
    "grid_end_slot": sa.Column("grid_end_slot", sa.Integer(), nullable=True),
}


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "timetable_session" not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns("timetable_session")}
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("timetable_session", column)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "timetable_session" not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns("timetable_session")}
    for name in reversed(list(_COLUMNS)):
        if name in existing:
            op.drop_column("timetable_session", name)

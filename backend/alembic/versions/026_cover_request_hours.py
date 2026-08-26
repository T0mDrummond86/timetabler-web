"""Let a pending cover request carry hours set by hand.

Cover hours are worked out from the class the lecturer is covering, which is
right almost every time. It is not right when the arrangement and the timetable
disagree: someone asked to take only the back half of a three-hour class, or a
session that finished early, or two people splitting one cover between them.
Until now the only way to record that was to log the wrong figure and correct
the lecturer's balance somewhere else.

Null keeps the derived behaviour, so every existing request is untouched and
the column only means something where somebody has deliberately set it.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "026_cover_request_hours"
down_revision = "025_two_factor_auth"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "cover_request", "hours"):
        op.add_column("cover_request", sa.Column("hours", sa.Float(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "cover_request", "hours"):
        op.drop_column("cover_request", "hours")

"""Record how long each logged cover job was.

Cover jobs only carried a display label ("09:00 - 12:00"), so cover time could
not be totalled against a lecturer. New jobs record hours exactly from the
booking's slot span; existing rows are backfilled by reading their label, and
anything unreadable is left NULL for the aggregation to treat as zero.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "021_cover_log_hours"
down_revision = "020_drop_staff_identifier"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "cover_log_entry" not in set(inspector.get_table_names()):
        return
    if _has_column(inspector, "cover_log_entry", "hours"):
        return

    op.add_column("cover_log_entry", sa.Column("hours", sa.Float(), nullable=True))

    # Backfill from the label using the same parser the app uses, so a row
    # logged before this migration totals the same as one logged after it.
    import sys
    from pathlib import Path

    domain = Path(__file__).resolve().parents[3] / "packages" / "domain"
    if str(domain) not in sys.path:
        sys.path.insert(0, str(domain))
    from timetable.core.cover_hours import hours_from_time_label

    rows = bind.execute(
        sa.text("SELECT id, time_label FROM cover_log_entry")
    ).fetchall()
    for row_id, label in rows:
        hours = hours_from_time_label(label)
        if hours is None:
            continue
        bind.execute(
            sa.text("UPDATE cover_log_entry SET hours = :h WHERE id = :i"),
            {"h": hours, "i": row_id},
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "cover_log_entry", "hours"):
        op.drop_column("cover_log_entry", "hours")

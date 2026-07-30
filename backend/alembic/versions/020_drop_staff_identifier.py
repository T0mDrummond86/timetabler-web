"""Drop staff.staff_identifier.

The user-entered Staff ID is no longer used for identifying or authorising
anyone, so the column and its contents are removed rather than left holding
personal identifiers nothing reads.

Irreversible by design: downgrade re-creates the column but cannot restore the
values, which is the point of the change.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "020_drop_staff_identifier"
down_revision = "019_session_settings"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "staff", "staff_identifier"):
        op.drop_column("staff", "staff_identifier")


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "staff", "staff_identifier"):
        op.add_column(
            "staff", sa.Column("staff_identifier", sa.String(length=80), nullable=True)
        )

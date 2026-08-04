"""Let a class custodian be set by hand.

The custodian is otherwise derived — whoever delivers the class most often —
which is right most of the time but cannot express "this one is Dana's, whoever
happens to be teaching it this semester". A null override keeps the derived
answer, so nothing changes for classes nobody has touched.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "022_unit_custodian_override"
down_revision = "021_cover_log_hours"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "unit" not in set(inspector.get_table_names()):
        return
    if _has_column(inspector, "unit", "custodian_staff_id"):
        return
    # No FK constraint: staff rows are replaced wholesale by session restore,
    # and an override pointing at a since-deleted lecturer should fall back to
    # the derived custodian rather than block the restore.
    op.add_column(
        "unit", sa.Column("custodian_staff_id", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "unit", "custodian_staff_id"):
        op.drop_column("unit", "custodian_staff_id")

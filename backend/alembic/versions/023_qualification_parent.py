"""Remember which qualification a stage was split from.

Stages are separate qualification records so each can be timetabled on its own,
but they are still one qualification as far as the curriculum is concerned. This
records that, so the family can be shown and exported together.

Null means "not a stage of anything" — which is every qualification that has
never been split, and reads correctly as already whole.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "023_qualification_parent"
down_revision = "022_unit_custodian_override"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "qualification" not in set(inspector.get_table_names()):
        return
    if _has_column(inspector, "qualification", "parent_qualification_id"):
        return
    # No FK constraint, matching the custodian override: session restore
    # replaces qualification rows wholesale, and a parent id left pointing at a
    # since-replaced row must degrade to "no parent" rather than block the
    # restore outright.
    op.add_column(
        "qualification",
        sa.Column("parent_qualification_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "qualification", "parent_qualification_id"):
        op.drop_column("qualification", "parent_qualification_id")

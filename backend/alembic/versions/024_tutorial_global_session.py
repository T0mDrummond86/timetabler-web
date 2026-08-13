"""Mark a global workspace as somebody's tutorial group.

Tutorial sandboxes need a global workspace of their own: the tutorials cover
global features — the cover log, the calendar, cross-session views — and every
one of those writes real rows. Pointed at the working group, practice would
land in the records people actually rely on.

A flag rather than a name convention, because the group is the user's and they
may rename it; the guarantee that a sandbox never joins the working group has
to survive that.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "024_tutorial_global"
down_revision = "023_qualification_parent"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "global_session" not in set(inspector.get_table_names()):
        return
    if _has_column(inspector, "global_session", "is_tutorial"):
        return
    op.add_column(
        "global_session",
        sa.Column("is_tutorial", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "global_session", "is_tutorial"):
        op.drop_column("global_session", "is_tutorial")

"""Require users to set a new password after admin-assigned defaults."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "007_must_change_password"
down_revision = "006_username_admin_global_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = {c["name"] for c in inspect(conn).get_columns("user_account")}
    if "must_change_password" not in cols:
        op.add_column(
            "user_account",
            sa.Column(
                "must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    cols = {c["name"] for c in inspect(conn).get_columns("user_account")}
    if "must_change_password" in cols:
        op.drop_column("user_account", "must_change_password")

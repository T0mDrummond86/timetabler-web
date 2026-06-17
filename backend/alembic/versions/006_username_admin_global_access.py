"""Username login, admin flags, and global workspace user access."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "006_username_admin_global_access"
down_revision = "005_clash_check_settings"
branch_labels = None
depends_on = None


def _user_columns(conn) -> set[str]:
    return {c["name"] for c in inspect(conn).get_columns("user_account")}


def upgrade() -> None:
    conn = op.get_bind()
    cols = _user_columns(conn)

    if "username" not in cols:
        op.add_column("user_account", sa.Column("username", sa.String(80), nullable=True))
    if "is_admin" not in cols:
        op.add_column(
            "user_account",
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "is_active" not in cols:
        op.add_column(
            "user_account",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )

    if conn.dialect.name == "postgresql":
        conn.execute(
            sa.text(
                "UPDATE user_account SET username = split_part(email, '@', 1) "
                "WHERE username IS NULL AND email IS NOT NULL"
            )
        )
    else:
        conn.execute(
            sa.text(
                "UPDATE user_account SET username = substr(email, 1, instr(email, '@') - 1) "
                "WHERE username IS NULL AND email IS NOT NULL AND instr(email, '@') > 0"
            )
        )
    conn.execute(
        sa.text(
            "UPDATE user_account SET username = 'user_' || id "
            "WHERE username IS NULL OR username = ''"
        )
    )

    cols = _user_columns(conn)
    if "username" in cols:
        op.alter_column("user_account", "username", nullable=False)

    inspector = inspect(conn)
    uk_names = {c["name"] for c in inspector.get_unique_constraints("user_account")}
    if "user_account_username_uk" not in uk_names:
        op.create_unique_constraint("user_account_username_uk", "user_account", ["username"])

    op.alter_column("user_account", "email", existing_type=sa.String(320), nullable=True)

    if "global_session_user_access" not in inspector.get_table_names():
        op.create_table(
            "global_session_user_access",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "global_session_id",
                sa.Integer(),
                sa.ForeignKey("global_session.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("user_account.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "granted_by_id",
                sa.Integer(),
                sa.ForeignKey("user_account.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("granted_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "global_session_id", "user_id", name="global_session_user_access_uk"
            ),
        )
        op.create_index(
            "ix_global_session_user_access_global_session_id",
            "global_session_user_access",
            ["global_session_id"],
        )
        op.create_index(
            "ix_global_session_user_access_user_id",
            "global_session_user_access",
            ["user_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if "global_session_user_access" in inspect(conn).get_table_names():
        op.drop_table("global_session_user_access")
    op.drop_constraint("user_account_username_uk", "user_account", type_="unique")
    op.drop_column("user_account", "is_active")
    op.drop_column("user_account", "is_admin")
    op.drop_column("user_account", "username")
    op.alter_column("user_account", "email", existing_type=sa.String(320), nullable=False)

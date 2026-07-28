"""Per-user edit/read-only access, per session and per global session group.

Adds an explicit permission layer on top of the existing visibility rules:

* ``session_user_access`` — a user's level on one timetable session.
* ``global_session_user_access.level`` — that user's default across the group.
* ``global_session.created_by_id`` — the group's creator, who may manage access.

Existing access rows are backfilled to "edit" so nobody who can edit today
loses the ability when this ships.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "017_session_access"
down_revision = "016_cover_group_rename"
branch_labels = None
depends_on = None


def _has_table(inspector, name: str) -> bool:
    return name in set(inspector.get_table_names())


def _has_column(inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_table(inspector, "session_user_access"):
        op.create_table(
            "session_user_access",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "timetable_session_id",
                sa.Integer(),
                sa.ForeignKey("timetable_session.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("user_account.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("level", sa.String(length=16), nullable=False, server_default="edit"),
            sa.Column(
                "granted_by_id",
                sa.Integer(),
                sa.ForeignKey("user_account.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "timetable_session_id", "user_id", name="session_user_access_uk"
            ),
        )

    if not _has_column(inspector, "global_session_user_access", "level"):
        op.add_column(
            "global_session_user_access",
            sa.Column("level", sa.String(length=16), nullable=False, server_default="edit"),
        )
        # Anyone with group access today can edit today — keep it that way.
        op.execute("UPDATE global_session_user_access SET level = 'edit' WHERE level IS NULL")

    if not _has_column(inspector, "global_session", "created_by_id"):
        op.add_column(
            "global_session",
            sa.Column(
                "created_by_id",
                sa.Integer(),
                sa.ForeignKey("user_account.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_column(inspector, "global_session", "created_by_id"):
        op.drop_column("global_session", "created_by_id")
    if _has_column(inspector, "global_session_user_access", "level"):
        op.drop_column("global_session_user_access", "level")
    if _has_table(inspector, "session_user_access"):
        op.drop_table("session_user_access")

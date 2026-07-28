"""Give every global workspace an owner.

The workspace's creator is now the person who sets access levels and invites
members, but workspaces created before 017 have no ``created_by_id``, which
would leave them with nobody able to administer them. Backfill those to the
organisation's owner-role member so no workspace is orphaned.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "018_global_session_owner"
down_revision = "017_session_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "global_session" not in tables or "membership" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("global_session")}
    if "created_by_id" not in cols:
        return

    # Lowest-id owner of the workspace's organisation — deterministic, and
    # always someone who could already administer the whole org.
    bind.execute(
        sa.text(
            """
            UPDATE global_session AS g
               SET created_by_id = (
                     SELECT m.user_id
                       FROM membership AS m
                      WHERE m.organization_id = g.organization_id
                        AND m.role = 'owner'
                      ORDER BY m.user_id
                      LIMIT 1
                   )
             WHERE g.created_by_id IS NULL
            """
        )
    )


def downgrade() -> None:
    # The pre-018 state cannot be distinguished from a legitimately set owner.
    pass

"""Initial schema: auth + domain with timetable_session_id."""

from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dev bootstrap uses create_all(); revision documents Phase 1 schema.
    pass


def downgrade() -> None:
    pass

"""Initial schema: auth + domain with timetable_session_id."""

from alembic import op

from timetable.core.models import Base
from timetable.core.tenancy_models import (  # noqa: F401 (registers tables)
    Membership,
    Organization,
    TimetableSession,
    User,
)

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())

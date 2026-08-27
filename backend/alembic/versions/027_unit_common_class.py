"""Mark a class as one delivered under several qualifications.

The same class often arrives once per qualification, because each course study
plan is imported on its own. Class names are unique within a session, so those
duplicates cannot look identical -- they come in as "ICTNWK540 CertIV" and
"ICTNWK540 Dip" -- and nothing on the row proves they are the same delivery.
Shared unit codes are a hint, not proof: two classes can legitimately teach the
same code. So the judgement is recorded by hand, and this column holds it until
somebody acts on it.

Defaults to 0, so every existing class starts unmarked.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "027_unit_common_class"
down_revision = "026_cover_request_hours"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not _has_column(inspector, "unit", "common_class"):
        op.add_column(
            "unit",
            sa.Column("common_class", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _has_column(inspector, "unit", "common_class"):
        op.drop_column("unit", "common_class")

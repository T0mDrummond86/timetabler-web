"""Add unit_lap table for uploaded Learning & Assessment Plans."""

from alembic import op
import sqlalchemy as sa

revision = "003_unit_lap"
down_revision = "002_staff_cost_centre"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unit_lap",
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("timetable_session_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["timetable_session_id"], ["timetable_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["unit.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("unit_id"),
    )
    op.create_index("ix_unit_lap_timetable_session_id", "unit_lap", ["timetable_session_id"])


def downgrade() -> None:
    op.drop_index("ix_unit_lap_timetable_session_id", table_name="unit_lap")
    op.drop_table("unit_lap")

"""Two-factor authentication: TOTP secrets, recovery codes, trusted devices.

Timetables name every lecturer's whereabouts for a term, so a stolen password
is worth more here than the app's size suggests. Second factor is TOTP — no
mail or SMS delivery to stand up, and nothing leaves the VM.

Three pieces:
  * the secret and the moment enrolment was confirmed, on the user
  * recovery codes, hashed, single-use — the way back in without the phone
  * trusted devices, hashed and expiring, so the phone app does not ask weekly
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "025_two_factor_auth"
down_revision = "024_tutorial_global"
branch_labels = None
depends_on = None


def _tables(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in _tables(inspector):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "user_account" not in _tables(inspector):
        return

    if not _has_column(inspector, "user_account", "totp_secret"):
        op.add_column("user_account", sa.Column("totp_secret", sa.String(64), nullable=True))
    if not _has_column(inspector, "user_account", "totp_confirmed_at"):
        # Null means "not enrolled yet" — which is every existing account, and
        # is exactly what the enrolment block keys on.
        op.add_column(
            "user_account", sa.Column("totp_confirmed_at", sa.DateTime(), nullable=True)
        )
    if not _has_column(inspector, "user_account", "totp_failed_attempts"):
        op.add_column(
            "user_account",
            sa.Column(
                "totp_failed_attempts", sa.Integer(), nullable=False, server_default="0"
            ),
        )
    if not _has_column(inspector, "user_account", "totp_locked_until"):
        op.add_column(
            "user_account", sa.Column("totp_locked_until", sa.DateTime(), nullable=True)
        )

    if "user_recovery_code" not in _tables(inspector):
        op.create_table(
            "user_recovery_code",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("user_account.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            # Hashed, never stored in the clear: a recovery code is a password.
            sa.Column("code_hash", sa.String(128), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if "user_trusted_device" not in _tables(inspector):
        op.create_table(
            "user_trusted_device",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("user_account.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("token_hash", sa.String(128), nullable=False, index=True),
            sa.Column("label", sa.String(120), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = _tables(inspector)
    if "user_trusted_device" in tables:
        op.drop_table("user_trusted_device")
    if "user_recovery_code" in tables:
        op.drop_table("user_recovery_code")
    for column in (
        "totp_locked_until",
        "totp_failed_attempts",
        "totp_confirmed_at",
        "totp_secret",
    ):
        if _has_column(inspector, "user_account", column):
            op.drop_column("user_account", column)

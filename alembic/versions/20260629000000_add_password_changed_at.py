"""Add password_changed_at column to users table.

Allows invalidating tokens issued before the user's last password change.
Existing users get NULL which means the check is skipped (backward compat).

Revision ID: 20260629000000
Revises: 20260626000000
Create Date: 2026-06-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260629000000"
down_revision: Union[str, None] = "20260626000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Set each time the password is changed or reset. Used to invalidate tokens issued before this timestamp.",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")

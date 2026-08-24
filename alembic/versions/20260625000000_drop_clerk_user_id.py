"""Drop clerk_user_id column from users table.

Clerk authentication has been fully removed from the application.
The clerk_user_id column is no longer referenced by any code.

Revision ID: 20260625000000
Revises: 20260623000005
Create Date: 2026-06-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260625000000"
down_revision: Union[str, None] = "20260623000005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the unique index on clerk_user_id first (PostgreSQL requires this
    # before dropping the column if there's an associated index)
    op.drop_index("ix_users_clerk_user_id", table_name="users")
    # Drop the column
    op.drop_column("users", "clerk_user_id")


def downgrade() -> None:
    # Re-add the column (nullable — Clerk is no longer active so all rows get NULL)
    op.add_column(
        "users",
        sa.Column("clerk_user_id", sa.String(length=255), nullable=True),
    )
    # Re-create the unique index
    op.create_index(
        "ix_users_clerk_user_id",
        "users",
        ["clerk_user_id"],
        unique=True,
    )

"""Add an explicit UNIQUE constraint on users.email.

The initial migration (5c82d1dc0a22) created a unique INDEX on email
(op.create_index(..., unique=True)), but the Column definition itself
did not carry unique=True at the migration level — only at the ORM
model level.  This migration adds a proper table-level UNIQUE constraint
so the schema is self-documenting and matches the SQLAlchemy model.

Revision ID: 20260701000001
Revises: 20260701000000
Create Date: 2026-07-01 01:00:00.000000


Note: revision 20260701000000's down_revision was corrected to
"8cf5fbf57966" so the migration chain is now linear:
  20260629000000 -> 8cf5fbf57966 -> 20260701000000 -> 20260701000001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260701000001"
down_revision: Union[str, None] = "20260701000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the existing unique index first (PostgreSQL requires this)
    op.drop_index("ix_users_email", table_name="users")
    # Create an explicit table-level UNIQUE constraint.
    # PostgreSQL automatically creates a unique index behind the scenes when
    # a UNIQUE constraint is added, so we still get the query performance.
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    # Drop the constraint
    op.drop_constraint("uq_users_email", "users", type_="unique")
    # Recreate the original unique index
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

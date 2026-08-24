"""add address column to user_locations

Revision ID: 20260818000000
Revises: 20260817000000
Create Date: 2026-08-18

"""
from alembic import op
import sqlalchemy as sa

revision = "20260818000000"
down_revision = "20260817000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_locations",
        sa.Column("address", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_locations", "address")

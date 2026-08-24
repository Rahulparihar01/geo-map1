"""drop altitude and speed columns from location tables

Revision ID: 20260817000000
Revises: 20260813_cleanup_stripe_legacy
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa

revision = "20260817000000"
down_revision = "20260813_cleanup_stripe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("user_locations", "altitude")
    op.drop_column("user_locations", "speed")
    op.drop_column("location_history", "altitude")
    op.drop_column("location_history", "speed")


def downgrade() -> None:
    op.add_column("location_history", sa.Column("speed", sa.Float(), nullable=True))
    op.add_column("location_history", sa.Column("altitude", sa.Float(), nullable=True))
    op.add_column("user_locations", sa.Column("speed", sa.Float(), nullable=True))
    op.add_column("user_locations", sa.Column("altitude", sa.Float(), nullable=True))

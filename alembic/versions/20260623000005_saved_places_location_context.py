"""Add save-location context to user_saved_places.

Allows users to save the same place multiple times with different
location contexts. Adds saved_location_lat/lon columns and replaces
the unique constraint with a plain index.

Revision ID: 20260623000005
Revises: 20260623000001
Create Date: 2026-06-23 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260623000005"
down_revision: Union[str, None] = "20260623000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add location-context columns (nullable — existing rows get NULL)
    op.add_column(
        "user_saved_places",
        sa.Column("saved_location_lat", sa.Float(), nullable=True),
    )
    op.add_column(
        "user_saved_places",
        sa.Column("saved_location_lon", sa.Float(), nullable=True),
    )

    # Remove the unique constraint so the same place can be saved
    # multiple times with different location contexts
    op.drop_constraint("uq_user_saved_place", "user_saved_places", type_="unique")

    # Add a plain composite index for efficient user+place lookups
    op.create_index(
        "ix_user_saved_places_user_place",
        "user_saved_places",
        ["user_id", "place_id"],
    )


def downgrade() -> None:
    # Drop the composite index
    op.drop_index("ix_user_saved_places_user_place", table_name="user_saved_places")

    # Restore the unique constraint
    op.create_unique_constraint(
        "uq_user_saved_place", "user_saved_places", ["user_id", "place_id"]
    )

    # Remove location-context columns
    op.drop_column("user_saved_places", "saved_location_lon")
    op.drop_column("user_saved_places", "saved_location_lat")

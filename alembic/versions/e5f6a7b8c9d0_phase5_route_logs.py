from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "route_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Origin coordinates (user's GPS location at time of request)
        sa.Column("origin_latitude", sa.Float(), nullable=False),
        sa.Column("origin_longitude", sa.Float(), nullable=False),
        # Destination — may be a Google place or a raw coordinate
        sa.Column("destination_place_id", sa.String(length=255), nullable=True),
        sa.Column("destination_latitude", sa.Float(), nullable=True),
        sa.Column("destination_longitude", sa.Float(), nullable=True),
        # Route parameters
        sa.Column("travel_mode", sa.String(length=20), nullable=False),
        # Result metrics (null if the route was served from cache)
        sa.Column("distance_meters", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        # Whether the result was served from Redis cache
        sa.Column("from_cache", sa.Boolean(), nullable=False, server_default="false"),
        # Audit timestamp
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_route_logs_id", "route_logs", ["id"])
    op.create_index("ix_route_logs_user_id", "route_logs", ["user_id"])
    op.create_index(
        "ix_route_logs_destination_place_id",
        "route_logs",
        ["destination_place_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_route_logs_destination_place_id", table_name="route_logs")
    op.drop_index("ix_route_logs_user_id", table_name="route_logs")
    op.drop_index("ix_route_logs_id", table_name="route_logs")
    op.drop_table("route_logs")

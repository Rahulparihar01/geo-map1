"""add place unlock and ai usage tracking

Revision ID: 20260807120839
Revises: 20260701000002
Create Date: 2026-08-07 12:08:39
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260807120839"
down_revision: Union[str, None] = "20260701000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table(
        "ai_usage_trackers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "total_questions_asked", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "reset_type",
            sa.String(length=20),
            nullable=False,
            server_default="lifetime",
        ),
        sa.Column("last_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_trackers_id", "ai_usage_trackers", ["id"])
    op.create_index(
        "ix_ai_usage_trackers_user_id", "ai_usage_trackers", ["user_id"], unique=True
    )

    op.create_table(
        "place_category_prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("category_label", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("token_cost", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_place_category_prices_id", "place_category_prices", ["id"])
    op.create_index(
        "ix_place_category_prices_category",
        "place_category_prices",
        ["category"],
        unique=True,
    )

    op.create_table(
        "place_unlocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("tokens_spent", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=500), nullable=True),
        sa.Column("formatted_address", sa.String(length=1000), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "unlocked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "place_id", name="uq_user_place_unlock"),
    )
    op.create_index("ix_place_unlocks_id", "place_unlocks", ["id"])
    op.create_index("ix_place_unlocks_user_id", "place_unlocks", ["user_id"])
    op.create_index("ix_place_unlocks_place_id", "place_unlocks", ["place_id"])
    op.create_index("ix_place_unlocks_unlocked_at", "place_unlocks", ["unlocked_at"])

    op.execute("""
        INSERT INTO place_category_prices (category, category_label, description, token_cost, is_active)
        VALUES 
            ('tourist_attraction', 'Tourist Places & Attractions', 
             'Museums, monuments, temples, churches, mosques, parks, historical landmarks, zoos, aquariums', 
             10, true),
            ('restaurant', 'Food & Restaurants', 
             'Restaurants, cafes, bars, bakeries, fast food, fine dining', 
             5, true),
            ('shopping_mall', 'Shopping Malls', 
             'Shopping centers, malls, supermarkets, retail stores, markets', 
             5, true)
    """)


def downgrade() -> None:
    op.drop_index("ix_place_unlocks_unlocked_at", "place_unlocks")
    op.drop_index("ix_place_unlocks_place_id", "place_unlocks")
    op.drop_index("ix_place_unlocks_user_id", "place_unlocks")
    op.drop_index("ix_place_unlocks_id", "place_unlocks")
    op.drop_table("place_unlocks")

    op.drop_index("ix_place_category_prices_category", "place_category_prices")
    op.drop_index("ix_place_category_prices_id", "place_category_prices")
    op.drop_table("place_category_prices")

    op.drop_index("ix_ai_usage_trackers_user_id", "ai_usage_trackers")
    op.drop_index("ix_ai_usage_trackers_id", "ai_usage_trackers")
    op.drop_table("ai_usage_trackers")

"""update place unlock with question tracking

Revision ID: 20260807122541
Revises: 20260807120839
Create Date: 2026-08-07 12:25:41
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260807122541"
down_revision: Union[str, None] = "20260807120839"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.drop_constraint("uq_user_place_unlock", "place_unlocks", type_="unique")

    op.add_column(
        "place_unlocks",
        sa.Column("questions_used", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "place_unlocks",
        sa.Column("questions_limit", sa.Integer(), nullable=False, server_default="15"),
    )
    op.add_column(
        "place_unlocks",
        sa.Column("is_expired", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "place_unlocks",
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_place_unlocks_user_place_active",
        "place_unlocks",
        ["user_id", "place_id", "is_expired"],
    )

    op.add_column(
        "place_category_prices",
        sa.Column("questions_limit", sa.Integer(), nullable=False, server_default="15"),
    )

    op.execute("""
        UPDATE place_category_prices
        SET token_cost = 10, questions_limit = 15
        WHERE is_active = true
    """)


def downgrade() -> None:

    op.drop_index("ix_place_unlocks_user_place_active", "place_unlocks")

    op.drop_column("place_unlocks", "expired_at")
    op.drop_column("place_unlocks", "is_expired")
    op.drop_column("place_unlocks", "questions_limit")
    op.drop_column("place_unlocks", "questions_used")

    op.create_unique_constraint(
        "uq_user_place_unlock", "place_unlocks", ["user_id", "place_id"]
    )

    op.drop_column("place_category_prices", "questions_limit")

"""
Create user_saved_places and place_visit_logs tables.

Revision ID: 20260623000001
Revises: 20260623000000
Create Date: 2026-06-23 06:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260623000001"
down_revision: Union[str, None] = "20260623000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── user_saved_places ──────────────────────────────────────────────
    op.create_table(
        "user_saved_places",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("place_id", sa.String(length=255), nullable=False, index=True),
        sa.Column("display_name", sa.String(length=500), nullable=True),
        sa.Column("formatted_address", sa.Text(), nullable=True),
        sa.Column("primary_type", sa.String(length=100), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column(
            "is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "saved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "place_id", name="uq_user_saved_place"),
    )
    op.create_index(
        op.f("ix_user_saved_places_id"), "user_saved_places", ["id"], unique=False
    )

    # ── place_visit_logs ───────────────────────────────────────────────
    op.create_table(
        "place_visit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("place_id", sa.String(length=255), nullable=False, index=True),
        sa.Column("display_name", sa.String(length=500), nullable=True),
        sa.Column("formatted_address", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("rating_given", sa.Integer(), nullable=True),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column("with_whom", sa.String(length=100), nullable=True),
        sa.Column("mood", sa.String(length=50), nullable=True),
        sa.Column(
            "visited_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_place_visit_logs_id"), "place_visit_logs", ["id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_place_visit_logs_id"), table_name="place_visit_logs")
    op.drop_table("place_visit_logs")
    op.drop_index(op.f("ix_user_saved_places_id"), table_name="user_saved_places")
    op.drop_table("user_saved_places")

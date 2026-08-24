"""Add primary_type column to place_visit_logs for stats grouping.

Allows the /visits/stats endpoint to group visits by category without a JOIN
or missing column error.

Revision ID: 20260626000000
Revises: 20260625000001
Create Date: 2026-06-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260626000000"
down_revision: Union[str, None] = "20260625000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "place_visit_logs",
        sa.Column("primary_type", sa.String(length=100), nullable=True),
    )
    op.create_index(
        op.f("ix_place_visit_logs_primary_type"),
        "place_visit_logs",
        ["primary_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_place_visit_logs_primary_type"),
        table_name="place_visit_logs",
    )
    op.drop_column("place_visit_logs", "primary_type")

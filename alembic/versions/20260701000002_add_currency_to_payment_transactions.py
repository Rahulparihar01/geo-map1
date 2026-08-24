"""Add currency column to payment_transactions.

Stores the 3-letter ISO currency code of the Stripe charge (always "USD"
for this application).  Previously the currency was implied but never
explicitly stored in the database.

Revision ID: 20260701000002
Revises: 20260701000001
Create Date: 2026-07-01 02:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260701000002"
down_revision: Union[str, None] = "20260701000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_transactions",
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
            comment="3-letter ISO currency code of the Stripe charge (always USD)",
        ),
    )


def downgrade() -> None:
    op.drop_column("payment_transactions", "currency")

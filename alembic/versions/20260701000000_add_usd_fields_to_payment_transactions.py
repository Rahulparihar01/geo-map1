"""Add amount_usd and exchange_rate to payment_transactions.

Stores the USD amount actually charged to Stripe and the INR/USD rate
used at the time of each payment intent creation.

Revision ID: 20260701000000
Revises: 8cf5fbf57966
Create Date: 2026-07-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260701000000"
down_revision: Union[str, None] = "8cf5fbf57966"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_transactions",
        sa.Column(
            "amount_usd",
            sa.Float(),
            nullable=True,
            comment="Converted amount in USD charged to Stripe (e.g. 1.80)",
        ),
    )
    op.add_column(
        "payment_transactions",
        sa.Column(
            "exchange_rate",
            sa.Float(),
            nullable=True,
            comment="INR per 1 USD at time of payment (e.g. 83.52)",
        ),
    )


def downgrade() -> None:
    op.drop_column("payment_transactions", "exchange_rate")
    op.drop_column("payment_transactions", "amount_usd")

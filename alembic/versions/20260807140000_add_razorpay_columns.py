from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260807140000"
down_revision: Union[str, None] = "20260807122541"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- Provider discriminator -------------------------------------------------
    op.add_column(
        "payment_transactions",
        sa.Column(
            "provider",
            sa.String(length=16),
            server_default="stripe",
            nullable=False,
            comment="Payment provider ('stripe' for legacy rows, 'razorpay' for new)",
        ),
    )

    # ---- Razorpay identifiers --------------------------------------------------
    op.add_column(
        "payment_transactions",
        sa.Column("razorpay_order_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "payment_transactions",
        sa.Column("razorpay_payment_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "payment_transactions",
        sa.Column("razorpay_signature", sa.String(length=255), nullable=True),
    )

    op.create_index(
        "ix_payment_transactions_razorpay_order_id",
        "payment_transactions",
        ["razorpay_order_id"],
        unique=True,
    )
    op.create_index(
        "ix_payment_transactions_razorpay_payment_id",
        "payment_transactions",
        ["razorpay_payment_id"],
        unique=False,
    )

    # ---- Legacy Stripe fields become optional ----------------------------------
    # Razorpay transactions have no PaymentIntent, so the column must accept NULL.
    # The column is kept (not dropped) so historical Stripe rows remain intact.
    op.alter_column(
        "payment_transactions",
        "stripe_payment_intent_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    # New rows default to INR (legacy rows keep their stored USD value).
    op.alter_column(
        "payment_transactions",
        "currency",
        existing_type=sa.String(length=3),
        server_default="INR",
        existing_server_default="USD",
    )


def downgrade() -> None:
    # WARNING: restoring NOT NULL on stripe_payment_intent_id fails if any
    # Razorpay rows exist. Run this downgrade only before Razorpay goes live.
    op.alter_column(
        "payment_transactions",
        "stripe_payment_intent_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "payment_transactions",
        "currency",
        existing_type=sa.String(length=3),
        server_default="USD",
        existing_server_default="INR",
    )

    op.drop_index(
        "ix_payment_transactions_razorpay_payment_id",
        table_name="payment_transactions",
    )
    op.drop_index(
        "ix_payment_transactions_razorpay_order_id",
        table_name="payment_transactions",
    )

    op.drop_column("payment_transactions", "razorpay_signature")
    op.drop_column("payment_transactions", "razorpay_payment_id")
    op.drop_column("payment_transactions", "razorpay_order_id")
    op.drop_column("payment_transactions", "provider")

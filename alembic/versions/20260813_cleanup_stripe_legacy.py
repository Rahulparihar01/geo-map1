"""Remove legacy Stripe payment fields and unused currency columns.

Stripe support ended; all payments now Razorpay (INR). This migration cleans up:
- provider column (always 'razorpay' now)
- stripe_payment_intent_id, stripe_client_secret (legacy fields)
- amount_usd, exchange_rate, currency (Stripe-era fields, not used for Razorpay)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260813_cleanup_stripe'
down_revision = '9a98d10e1fda'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop Stripe-specific columns
    op.drop_index('ix_payment_transactions_stripe_payment_intent_id', table_name='payment_transactions')
    op.drop_column('payment_transactions', 'stripe_payment_intent_id')
    op.drop_column('payment_transactions', 'stripe_client_secret')
    
    # Drop Stripe/legacy provider fields (always Razorpay now)
    op.drop_column('payment_transactions', 'provider')
    op.drop_column('payment_transactions', 'currency')
    op.drop_column('payment_transactions', 'amount_usd')
    op.drop_column('payment_transactions', 'exchange_rate')


def downgrade() -> None:
    # Re-add columns for rollback (though not recommended for production)
    op.add_column('payment_transactions', sa.Column('exchange_rate', sa.Float(), nullable=True))
    op.add_column('payment_transactions', sa.Column('amount_usd', sa.Float(), nullable=True))
    op.add_column('payment_transactions', sa.Column('currency', sa.String(3), server_default='INR', nullable=False))
    op.add_column('payment_transactions', sa.Column('provider', sa.String(20), server_default='razorpay', nullable=False))
    op.add_column('payment_transactions', sa.Column('stripe_client_secret', sa.String(255), nullable=True))
    op.add_column('payment_transactions', sa.Column('stripe_payment_intent_id', sa.String(255), nullable=True))
    op.create_index('ix_payment_transactions_stripe_payment_intent_id', 'payment_transactions', ['stripe_payment_intent_id'], unique=True)

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_credits_to_users"
down_revision = "1cfd5b0be024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add credits column to users table with default of 50
    op.add_column(
        "users", sa.Column("credits", sa.Integer(), server_default="50", nullable=False)
    )


def downgrade() -> None:
    # Remove credits column on downgrade
    op.drop_column("users", "credits")

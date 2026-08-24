from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260616161353"
down_revision = "a633cd1c3123"
branch_labels = None
depends_on = None


def upgrade():
    # Add place_id column to chat_conversations table
    op.add_column(
        "chat_conversations",
        sa.Column("place_id", sa.String(length=255), nullable=True),
    )

    # Add index on place_id for better query performance
    op.create_index(
        "ix_chat_conversations_place_id",
        "chat_conversations",
        ["place_id"],
        unique=False,
    )


def downgrade():
    # Remove index first
    op.drop_index("ix_chat_conversations_place_id", table_name="chat_conversations")

    # Remove column
    op.drop_column("chat_conversations", "place_id")

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "cb3b8c851c9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Before creating the unique index, clean up any existing duplicate
    # is_current=True rows that may have been created before this fix.
    # Keep only the most recently created row per user.
    op.execute("""
        UPDATE user_locations ul
        SET is_current = FALSE
        WHERE is_current = TRUE
          AND id NOT IN (
              SELECT DISTINCT ON (user_id) id
              FROM user_locations
              WHERE is_current = TRUE
              ORDER BY user_id, created_at DESC
          )
    """)

    op.create_index(
        index_name="uix_user_locations_single_current",
        table_name="user_locations",
        columns=["user_id"],
        unique=True,
        postgresql_where=sa.text("is_current = TRUE"),
    )


def downgrade() -> None:
    op.drop_index(
        index_name="uix_user_locations_single_current",
        table_name="user_locations",
    )

"""add_partial_unique_constraint_active_unlocks

Revision ID: 9a98d10e1fda
Revises: 20260807140000
Create Date: 2026-08-08 11:33:49.446700

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9a98d10e1fda"
down_revision: Union[str, None] = "20260807140000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX uq_user_place_active 
        ON place_unlocks (user_id, place_id) 
        WHERE is_expired = false
    """)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_user_place_active")

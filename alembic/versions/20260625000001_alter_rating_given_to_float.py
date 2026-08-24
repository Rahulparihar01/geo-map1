"""Change rating_given column from Integer to Float.

Allows decimal ratings (e.g. 4.5) in addition to whole numbers.

Revision ID: 20260625000001
Revises: 20260625000000
Create Date: 2026-06-25 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260625000001"
down_revision: Union[str, None] = "20260625000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL: change Integer to Float (double precision)
    # USING clause casts existing integer values to float automatically
    op.execute(
        "ALTER TABLE place_visit_logs "
        "ALTER COLUMN rating_given TYPE double precision "
        "USING rating_given::double precision"
    )


def downgrade() -> None:
    # Revert back to Integer. Float values will be truncated (rounded down).
    # This is lossy — e.g. 4.5 → 4, so warn against downgrade in production.
    op.execute(
        "ALTER TABLE place_visit_logs "
        "ALTER COLUMN rating_given TYPE integer "
        "USING CASE "
        "  WHEN rating_given IS NOT NULL THEN round(rating_given)::integer "
        "  ELSE NULL "
        "END"
    )

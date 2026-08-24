from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260620000000"
down_revision: Union[str, None] = "0fa91a232bae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update server_default for auth_provider to 'clerk'
    op.alter_column(
        "users",
        "auth_provider",
        existing_type=sa.String(length=20),
        server_default="clerk",
        nullable=False,
    )

    # 2. Backfill: any user with a clerk_user_id should have auth_provider = 'clerk'
    op.execute(
        "UPDATE users SET auth_provider = 'clerk' "
        "WHERE clerk_user_id IS NOT NULL AND auth_provider != 'clerk'"
    )

    # 3. Ensure credits default is 50
    op.alter_column(
        "users",
        "credits",
        existing_type=sa.Integer(),
        server_default="50",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "auth_provider",
        existing_type=sa.String(length=20),
        server_default="local",
        nullable=False,
    )
    # credits default rollback — keep at 50, no functional difference

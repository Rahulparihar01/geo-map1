from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "20260618190000"
down_revision: Union[str, tuple[str, str], None] = (
    "add_credits_to_users",
    "20260617120000",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0fa91a232bae"
down_revision: Union[str, None] = "20260619000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("clerk_user_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=20),
            server_default="local",
            nullable=False,
        ),
    )

    # hashed_password becomes nullable — Clerk users have no local password
    op.alter_column(
        "users", "hashed_password", existing_type=sa.VARCHAR(length=255), nullable=True
    )

    # Unique index on clerk_user_id for fast lookup during webhook sync
    op.create_index(
        op.f("ix_users_clerk_user_id"), "users", ["clerk_user_id"], unique=True
    )

    op.create_foreign_key(
        "fk_place_qa_sessions_user_id",  # constraint name
        "place_qa_sessions",  # source table
        "users",  # referent table
        ["user_id"],  # source columns
        ["id"],  # referent columns
        ondelete="CASCADE",  # delete sessions when user is deleted
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_place_qa_sessions_user_id", "place_qa_sessions", type_="foreignkey"
    )
    op.drop_index(op.f("ix_users_clerk_user_id"), table_name="users")
    op.alter_column(
        "users", "hashed_password", existing_type=sa.VARCHAR(length=255), nullable=False
    )
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "clerk_user_id")

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "a1b2c3d4e5f6"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_queries",
        sa.Column("from_cache_bool", sa.Boolean(), nullable=True, default=False),
    )
    op.execute("""
        UPDATE search_queries
        SET from_cache_bool = CASE
            WHEN from_cache = 'true' THEN TRUE
            ELSE FALSE
        END
        """)
    op.alter_column("search_queries", "from_cache_bool", nullable=False)
    op.drop_column("search_queries", "from_cache")
    op.alter_column("search_queries", "from_cache_bool", new_column_name="from_cache")
    op.execute("UPDATE users SET is_active = TRUE WHERE is_active IS NULL")
    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.true(),
    )


def downgrade() -> None:
    # Revert B29: make is_active nullable again
    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )

    # Revert B21: restore from_cache as String(5)
    op.add_column(
        "search_queries",
        sa.Column("from_cache_str", sa.String(5), nullable=True, default="false"),
    )
    op.execute("""
        UPDATE search_queries
        SET from_cache_str = CASE
            WHEN from_cache = TRUE THEN 'true'
            ELSE 'false'
        END
        """)
    op.alter_column("search_queries", "from_cache_str", nullable=False)
    op.drop_column("search_queries", "from_cache")
    op.alter_column("search_queries", "from_cache_str", new_column_name="from_cache")

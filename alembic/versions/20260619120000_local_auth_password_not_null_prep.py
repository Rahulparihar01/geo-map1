from alembic import op

revision = "20260619120000"
down_revision = "20260620000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='hashed_password'
            ) THEN
                ALTER TABLE users ADD COLUMN hashed_password VARCHAR(255);
            END IF;
        END$$;
    """)

    # Ensure auth_provider column exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='auth_provider'
            ) THEN
                ALTER TABLE users
                ADD COLUMN auth_provider VARCHAR(20) NOT NULL DEFAULT 'local';
            END IF;
        END$$;
    """)


def downgrade() -> None:
    # Nothing to reverse — these columns existed before
    pass

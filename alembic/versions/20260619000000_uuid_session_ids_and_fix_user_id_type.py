from alembic import op
import sqlalchemy as sa

revision = "20260619000000"
down_revision = "a9f3b1c2d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # Drop FK constraints referencing place_qa_sessions.id
    op.drop_constraint(
        "place_qa_messages_session_id_fkey",
        "place_qa_messages",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_place_questions_session_id",
        "place_questions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_place_answer_logs_session_id",
        "place_answer_logs",
        type_="foreignkey",
    )

    # Widen place_qa_sessions.id: VARCHAR(24) → VARCHAR(36)
    op.execute(
        "ALTER TABLE place_qa_sessions "
        "ALTER COLUMN id TYPE VARCHAR(36) USING id::VARCHAR"
    )

    # Fix user_id: VARCHAR(255) → INTEGER
    op.execute(
        "ALTER TABLE place_qa_sessions "
        "ALTER COLUMN user_id TYPE INTEGER USING user_id::INTEGER"
    )

    # Widen FK columns in child tables: VARCHAR(24) → VARCHAR(36)
    op.execute(
        "ALTER TABLE place_qa_messages "
        "ALTER COLUMN session_id TYPE VARCHAR(36) USING session_id::VARCHAR"
    )
    op.execute(
        "ALTER TABLE place_questions "
        "ALTER COLUMN session_id TYPE VARCHAR(36) USING session_id::VARCHAR"
    )
    op.execute(
        "ALTER TABLE place_answer_logs "
        "ALTER COLUMN session_id TYPE VARCHAR(36) USING session_id::VARCHAR"
    )

    # Restore FK constraints
    op.create_foreign_key(
        "place_qa_messages_session_id_fkey",
        "place_qa_messages",
        "place_qa_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_place_questions_session_id",
        "place_questions",
        "place_qa_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_place_answer_logs_session_id",
        "place_answer_logs",
        "place_qa_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. ai_chat_sessions: INTEGER PK → VARCHAR(36) UUID                  #
    #    ai_chat_messages:  INTEGER FK → VARCHAR(36)                       #
    # ------------------------------------------------------------------ #

    # Drop FK from ai_chat_messages → ai_chat_sessions
    op.drop_constraint(
        "ai_chat_messages_session_id_fkey",
        "ai_chat_messages",
        type_="foreignkey",
    )

    # Add a temporary column to hold the new UUID-format id
    op.add_column(
        "ai_chat_sessions",
        sa.Column("id_new", sa.String(36), nullable=True),
    )
    # Populate id_new from old integer id cast to text
    # (existing sessions keep their numeric string as id for continuity)
    op.execute("UPDATE ai_chat_sessions SET id_new = id::text")

    # Widen ai_chat_messages.session_id to VARCHAR(36)
    op.execute(
        "ALTER TABLE ai_chat_messages "
        "ALTER COLUMN session_id TYPE VARCHAR(36) USING session_id::text"
    )

    # Swap PK: drop old integer id, rename id_new → id
    op.drop_constraint("ai_chat_sessions_pkey", "ai_chat_sessions", type_="primary")
    op.drop_column("ai_chat_sessions", "id")
    op.alter_column(
        "ai_chat_sessions",
        "id_new",
        new_column_name="id",
        existing_type=sa.String(36),
        nullable=False,
    )
    op.create_primary_key("ai_chat_sessions_pkey", "ai_chat_sessions", ["id"])

    # Recreate index on ai_chat_sessions.id
    op.create_index(
        "ix_ai_chat_sessions_id",
        "ai_chat_sessions",
        ["id"],
        unique=False,
    )

    # Restore FK
    op.create_foreign_key(
        "ai_chat_messages_session_id_fkey",
        "ai_chat_messages",
        "ai_chat_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # ------------------------------------------------------------------ #
    # Reverse ai_chat changes: VARCHAR(36) → INTEGER PK                   #
    # ------------------------------------------------------------------ #
    op.drop_constraint(
        "ai_chat_messages_session_id_fkey",
        "ai_chat_messages",
        type_="foreignkey",
    )
    op.drop_index("ix_ai_chat_sessions_id", "ai_chat_sessions")

    op.add_column(
        "ai_chat_sessions",
        sa.Column("id_old", sa.Integer(), nullable=True),
    )
    # Only rows whose id is a plain integer string can be cast back
    op.execute("UPDATE ai_chat_sessions SET id_old = id::integer WHERE id ~ '^[0-9]+$'")

    op.execute(
        "ALTER TABLE ai_chat_messages "
        "ALTER COLUMN session_id TYPE INTEGER USING session_id::integer"
    )

    op.drop_constraint("ai_chat_sessions_pkey", "ai_chat_sessions", type_="primary")
    op.drop_column("ai_chat_sessions", "id")
    op.alter_column(
        "ai_chat_sessions",
        "id_old",
        new_column_name="id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_primary_key("ai_chat_sessions_pkey", "ai_chat_sessions", ["id"])
    op.create_foreign_key(
        "ai_chat_messages_session_id_fkey",
        "ai_chat_messages",
        "ai_chat_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ------------------------------------------------------------------ #
    # Reverse place_qa changes: VARCHAR(36) → VARCHAR(24) + user_id back  #
    # ------------------------------------------------------------------ #
    op.drop_constraint(
        "place_qa_messages_session_id_fkey", "place_qa_messages", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_place_questions_session_id", "place_questions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_place_answer_logs_session_id", "place_answer_logs", type_="foreignkey"
    )

    op.execute(
        "ALTER TABLE place_qa_sessions "
        "ALTER COLUMN id TYPE VARCHAR(24) USING id::VARCHAR"
    )
    op.execute(
        "ALTER TABLE place_qa_sessions "
        "ALTER COLUMN user_id TYPE VARCHAR(255) USING user_id::text"
    )
    op.execute(
        "ALTER TABLE place_qa_messages "
        "ALTER COLUMN session_id TYPE VARCHAR(24) USING session_id::VARCHAR"
    )
    op.execute(
        "ALTER TABLE place_questions "
        "ALTER COLUMN session_id TYPE VARCHAR(24) USING session_id::VARCHAR"
    )
    op.execute(
        "ALTER TABLE place_answer_logs "
        "ALTER COLUMN session_id TYPE VARCHAR(24) USING session_id::VARCHAR"
    )

    op.create_foreign_key(
        "place_qa_messages_session_id_fkey",
        "place_qa_messages",
        "place_qa_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_place_questions_session_id",
        "place_questions",
        "place_qa_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_place_answer_logs_session_id",
        "place_answer_logs",
        "place_qa_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )

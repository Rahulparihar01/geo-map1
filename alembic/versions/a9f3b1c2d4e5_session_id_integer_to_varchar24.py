from typing import Sequence, Union
from alembic import op

revision: str = "a9f3b1c2d4e5"
down_revision: Union[str, None] = "20260618190000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FK on place_qa_messages.session_id (CASCADE)
    op.drop_constraint(
        "place_qa_messages_session_id_fkey",
        "place_qa_messages",
        type_="foreignkey",
    )

    # FK on place_questions.session_id (SET NULL)
    op.drop_constraint(
        "fk_place_questions_session_id",
        "place_questions",
        type_="foreignkey",
    )

    # FK on place_answer_logs.session_id (SET NULL)
    op.drop_constraint(
        "fk_place_answer_logs_session_id",
        "place_answer_logs",
        type_="foreignkey",
    )

    op.execute("UPDATE place_questions SET session_id = NULL")
    op.execute("UPDATE place_answer_logs SET session_id = NULL")
    op.execute("TRUNCATE place_qa_sessions CASCADE")
    op.drop_index("ix_place_qa_sessions_id", table_name="place_qa_sessions")
    op.execute("ALTER TABLE place_qa_sessions " "ALTER COLUMN id DROP DEFAULT")
    op.execute(
        "ALTER TABLE place_qa_sessions "
        "ALTER COLUMN id TYPE VARCHAR(24) USING id::VARCHAR"
    )
    op.drop_index("ix_place_qa_messages_session_id", table_name="place_qa_messages")
    op.execute(
        "ALTER TABLE place_qa_messages "
        "ALTER COLUMN session_id TYPE VARCHAR(24) USING session_id::VARCHAR"
    )
    op.drop_index("ix_place_questions_session_id", table_name="place_questions")
    op.execute(
        "ALTER TABLE place_questions "
        "ALTER COLUMN session_id TYPE VARCHAR(24) USING session_id::VARCHAR"
    )

    op.drop_index("ix_place_answer_logs_session_id", table_name="place_answer_logs")
    op.execute(
        "ALTER TABLE place_answer_logs "
        "ALTER COLUMN session_id TYPE VARCHAR(24) USING session_id::VARCHAR"
    )
    op.create_index(
        op.f("ix_place_qa_sessions_id"),
        "place_qa_sessions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_qa_messages_session_id"),
        "place_qa_messages",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_questions_session_id"),
        "place_questions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_answer_logs_session_id"),
        "place_answer_logs",
        ["session_id"],
        unique=False,
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


def downgrade() -> None:
    # Drop FKs
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

    # Null audit rows
    op.execute("UPDATE place_questions SET session_id = NULL")
    op.execute("UPDATE place_answer_logs SET session_id = NULL")

    # Truncate sessions
    op.execute("TRUNCATE place_qa_sessions CASCADE")

    # Drop indexes
    op.drop_index("ix_place_qa_sessions_id", table_name="place_qa_sessions")
    op.drop_index("ix_place_qa_messages_session_id", table_name="place_qa_messages")
    op.drop_index("ix_place_questions_session_id", table_name="place_questions")
    op.drop_index("ix_place_answer_logs_session_id", table_name="place_answer_logs")

    # Revert column types
    op.execute(
        "ALTER TABLE place_qa_sessions "
        "ALTER COLUMN id TYPE INTEGER USING id::INTEGER"
    )
    op.execute(
        "ALTER TABLE place_qa_sessions "
        "ALTER COLUMN id SET DEFAULT nextval('place_qa_sessions_id_seq')"
    )
    op.execute(
        "ALTER TABLE place_qa_messages "
        "ALTER COLUMN session_id TYPE INTEGER USING session_id::INTEGER"
    )
    op.execute(
        "ALTER TABLE place_questions "
        "ALTER COLUMN session_id TYPE INTEGER USING session_id::INTEGER"
    )
    op.execute(
        "ALTER TABLE place_answer_logs "
        "ALTER COLUMN session_id TYPE INTEGER USING session_id::INTEGER"
    )

    # Recreate indexes
    op.create_index(
        op.f("ix_place_qa_sessions_id"),
        "place_qa_sessions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_qa_messages_session_id"),
        "place_qa_messages",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_questions_session_id"),
        "place_questions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_answer_logs_session_id"),
        "place_answer_logs",
        ["session_id"],
        unique=False,
    )

    # Recreate FKs
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
